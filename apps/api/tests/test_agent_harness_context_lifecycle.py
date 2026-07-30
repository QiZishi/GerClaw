"""Context inventory, early compression, and fail-closed projection tests."""

from __future__ import annotations

import pytest

from gerclaw_api.modules.agent_harness.context_snapshot import (
    ContextSnapshotError,
    ContextWindowManager,
    ConversationHistoryMessage,
    estimate_context_tokens,
)


def _history(count: int, *, width: int = 120) -> tuple[ConversationHistoryMessage, ...]:
    return tuple(
        ConversationHistoryMessage(
            role="user" if index % 2 == 0 else "assistant",
            text=f"第 {index} 轮: " + ("上下文" * width),
        )
        for index in range(count)
    )


def test_context_plan_accounts_for_every_required_source_before_model_call() -> None:
    manager = ContextWindowManager()
    history = _history(10)

    draft = manager.plan(
        history=history,
        session_summary="既有摘要" * 100,
        fixed_sections=(
            ("current_input", ("当前问题" * 100,)),
            ("profile", ("用户画像" * 100,)),
            ("clinical_state", ("临床状态" * 100,)),
            ("skills", ("技能定义" * 100,)),
            ("documents", ("上传文档" * 200,)),
            ("capability_results", ("能力结果" * 100,)),
            ("plan", ("动态计划" * 100,)),
        ),
        model_context_tokens=8_000,
        trigger_ratio=0.85,
        hard_stop_ratio=0.95,
        reserve_ratio=0.2,
        output_reserve_tokens=1_000,
        input_overhead_tokens=500,
        image_count=1,
        image_estimate_tokens=300,
        evidence_reserve_tokens=600,
    )

    assert draft.compression_required is True
    assert draft.history_budget_tokens < draft.history_tokens_before
    assert {item.source for item in draft.sections} == {
        "system_tools",
        "current_input",
        "profile",
        "clinical_state",
        "skills",
        "documents",
        "capability_results",
        "plan",
        "history",
        "history_summary",
        "images",
        "evidence_reserve",
    }


def test_context_plan_fails_before_compression_when_required_inputs_do_not_fit() -> None:
    with pytest.raises(
        ContextSnapshotError,
        match="CONTEXT_REQUIRED_INPUT_EXCEEDS_WINDOW",
    ):
        ContextWindowManager().plan(
            history=_history(1),
            session_summary="",
            fixed_sections=(("documents", ("文档" * 20_000,)),),
            model_context_tokens=2_000,
            trigger_ratio=0.85,
            hard_stop_ratio=0.95,
            reserve_ratio=0.2,
            output_reserve_tokens=500,
            input_overhead_tokens=500,
            image_count=0,
            image_estimate_tokens=300,
            evidence_reserve_tokens=300,
        )


def test_emergency_short_circuit_is_never_blocked_by_the_model_context_window() -> None:
    manager = ContextWindowManager()
    draft = manager.plan(
        history=(),
        session_summary="",
        fixed_sections=(("current_input", ("胸痛并呼吸困难。" * 10_000,)),),
        model_context_tokens=2_000,
        trigger_ratio=0.85,
        hard_stop_ratio=0.95,
        reserve_ratio=0.2,
        output_reserve_tokens=500,
        input_overhead_tokens=500,
        image_count=0,
        image_estimate_tokens=300,
        evidence_reserve_tokens=0,
        model_call_required=False,
    )

    projection = manager.finalize(
        draft,
        history=(),
        session_summary="",
        strategy="none",
    )

    assert projection.projection_mode == "deterministic_short_circuit"
    assert projection.estimated_tokens_after > projection.model_context_tokens


def test_extractive_fallback_preserves_critical_user_text_and_recent_turns() -> None:
    history = (
        ConversationHistoryMessage(role="user", text="我对青霉素过敏。"),
        ConversationHistoryMessage(role="assistant", text="这是一段很长的历史解释。" * 100),
        ConversationHistoryMessage(role="user", text="普通偏好信息。"),
        ConversationHistoryMessage(role="assistant", text="最近一次回复。"),
        ConversationHistoryMessage(role="user", text="最近一次追问。"),
    )

    retained, summary = ContextWindowManager().compress_extractively(
        history,
        token_budget=80,
    )

    assert "我对青霉素过敏。" in summary
    assert retained[-1].text == "最近一次追问。"
    assert "诊断为" not in summary
    assert estimate_context_tokens(summary, *(item.text for item in retained)) <= 80


def test_token_estimate_does_not_treat_four_chinese_bytes_as_one_token() -> None:
    assert estimate_context_tokens("老年患者用药安全") == 8


def test_finalize_rejects_a_projection_that_still_exceeds_trigger() -> None:
    manager = ContextWindowManager()
    history = _history(8)
    draft = manager.plan(
        history=history,
        session_summary="",
        fixed_sections=(("current_input", ("问题",)),),
        model_context_tokens=2_000,
        trigger_ratio=0.85,
        hard_stop_ratio=0.95,
        reserve_ratio=0.2,
        output_reserve_tokens=400,
        input_overhead_tokens=200,
        image_count=0,
        image_estimate_tokens=200,
        evidence_reserve_tokens=200,
    )

    with pytest.raises(ContextSnapshotError, match="CONTEXT_COMPRESSION_INSUFFICIENT"):
        manager.finalize(
            draft,
            history=history,
            session_summary="",
            strategy="deterministic-extractive-v1",
        )


def test_dual_thresholds_preserve_high_value_requirements_and_lineage() -> None:
    manager = ContextWindowManager()
    history = (
        ConversationHistoryMessage(
            role="user",
            text="必须保留我的目标：完成后要给出可复现的验收结果。",  # noqa: RUF001
            stable_id="message:goal-001",
        ),
        ConversationHistoryMessage(
            role="assistant",
            text="冗长的成功日志。" * 300,
            stable_id="message:log-001",
        ),
        ConversationHistoryMessage(
            role="user",
            text="我对青霉素过敏。",
            stable_id="message:allergy-001",
        ),
        ConversationHistoryMessage(
            role="assistant",
            text="最近一次有效回复。",
            stable_id="message:answer-001",
        ),
    )
    draft = manager.plan(
        history=history,
        session_summary="上一代摘要",
        fixed_sections=(("current_input", ("继续执行。",)),),
        model_context_tokens=1_200,
        trigger_ratio=0.7,
        hard_stop_ratio=0.9,
        reserve_ratio=0.15,
        output_reserve_tokens=200,
        input_overhead_tokens=100,
        image_count=0,
        image_estimate_tokens=100,
        evidence_reserve_tokens=100,
        unresolved_item_ids=("unknown:medication-dose", "conflict:blood-pressure"),
    )
    retained, summary = manager.compress_extractively(
        history,
        token_budget=draft.history_budget_tokens,
        existing_summary="上一代摘要",
    )
    projection = manager.finalize(
        draft,
        history=retained,
        session_summary=summary,
        strategy="deterministic-extractive-v1",
    )

    assert "必须保留我的目标" in summary
    assert "我对青霉素过敏" in "\n".join((summary, *(item.text for item in retained)))
    assert projection.schema_version == "context-projection-v2"
    assert projection.soft_trigger_tokens < projection.hard_stop_tokens
    assert set(projection.retained_message_ids) | set(projection.omitted_message_ids) == set(
        projection.source_message_ids
    )
    assert projection.source_range_start_id == "message:goal-001"
    assert projection.source_range_end_id == "message:answer-001"
    assert projection.unresolved_item_ids == (
        "unknown:medication-dose",
        "conflict:blood-pressure",
    )
    assert len(projection.summary_lineage_hashes) >= 1


def test_fixed_inputs_between_soft_and_hard_use_effective_limit_without_silent_drop() -> None:
    manager = ContextWindowManager()
    draft = manager.plan(
        history=(),
        session_summary="",
        fixed_sections=(("documents", ("资料" * 380,)),),
        model_context_tokens=1_000,
        trigger_ratio=0.6,
        hard_stop_ratio=0.9,
        reserve_ratio=0.1,
        output_reserve_tokens=100,
        input_overhead_tokens=50,
        image_count=0,
        image_estimate_tokens=100,
        evidence_reserve_tokens=50,
    )
    projection = manager.finalize(
        draft,
        history=(),
        session_summary="",
        strategy="none",
    )

    assert projection.soft_trigger_tokens < projection.effective_limit_tokens
    assert projection.effective_limit_tokens <= projection.hard_stop_tokens


def test_context_ratio_order_rejects_overlapping_soft_and_hard_boundaries() -> None:
    with pytest.raises(ValueError, match="soft trigger < hard stop"):
        ContextWindowManager().plan(
            history=(),
            session_summary="",
            fixed_sections=(),
            model_context_tokens=1_000,
            trigger_ratio=0.9,
            hard_stop_ratio=0.8,
            reserve_ratio=0.1,
            output_reserve_tokens=100,
            input_overhead_tokens=50,
            image_count=0,
            image_estimate_tokens=100,
            evidence_reserve_tokens=50,
        )
