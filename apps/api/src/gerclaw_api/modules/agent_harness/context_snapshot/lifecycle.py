"""Pre-model context inventory, early overflow detection, and safe projection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal

from gerclaw_api.modules.agent_harness.context_snapshot.models import (
    ContextProjectionManifestV2,
    ContextSnapshotError,
    ContextSourceBudget,
    ContextSourceName,
    ConversationHistoryMessage,
)
from gerclaw_api.token_estimation import estimate_text_tokens

_SEGMENT = re.compile(r"[^。！？!?\n]+(?:[。！？!?]+|\n+|$)")  # noqa: RUF001
_CLINICAL_CRITICAL = re.compile(
    r"过敏|药|剂量|停用|血压|血糖|心率|胸痛|呼吸困难|意识|偏瘫|"
    r"出血|自伤|跌倒|诊断|检查|化验|手术|住院|急诊|否认|没有|不"
)
_USER_REQUIREMENT_CRITICAL = re.compile(
    r"必须|不要|不能|禁止|要求|目标|验收|记住|优先|继续|中断|排队|修改|删除|更新"
)


def estimate_context_tokens(*values: str) -> int:
    """Conservative dependency-free UTF-8 estimate shared by projection."""

    return estimate_text_tokens(values)


@dataclass(frozen=True, slots=True)
class ContextWindowDraft:
    """Pre-compression decision based on every known model-visible source."""

    model_context_tokens: int
    soft_trigger_tokens: int
    hard_stop_tokens: int
    effective_limit_tokens: int
    target_tokens: int
    output_reserve_tokens: int
    history_budget_tokens: int
    estimated_tokens_before: int
    history_tokens_before: int
    history_message_count: int
    source_hash: str
    source_history: tuple[ConversationHistoryMessage, ...]
    source_message_ids: tuple[str, ...]
    summary_lineage_hashes: tuple[str, ...]
    unresolved_item_ids: tuple[str, ...]
    sections: tuple[ContextSourceBudget, ...]
    compression_required: bool
    model_call_required: bool


class ContextWindowManager:
    """Allocate history only after accounting for all required context."""

    def plan(
        self,
        *,
        history: tuple[ConversationHistoryMessage, ...],
        session_summary: str,
        fixed_sections: tuple[tuple[ContextSourceName, tuple[str, ...]], ...],
        model_context_tokens: int,
        trigger_ratio: float,
        hard_stop_ratio: float,
        reserve_ratio: float,
        output_reserve_tokens: int,
        input_overhead_tokens: int,
        image_count: int,
        image_estimate_tokens: int,
        evidence_reserve_tokens: int,
        history_cap_tokens: int | None = None,
        model_call_required: bool = True,
        unresolved_item_ids: tuple[str, ...] = (),
    ) -> ContextWindowDraft:
        if model_context_tokens <= 0:
            raise ValueError("model context size must be positive")
        if not 0 < reserve_ratio < trigger_ratio < hard_stop_ratio < 1:
            raise ValueError(
                "context ratios must satisfy 0 < reserve < soft trigger < hard stop < 1"
            )
        if (
            min(
                output_reserve_tokens,
                input_overhead_tokens,
                image_count,
                image_estimate_tokens,
                evidence_reserve_tokens,
            )
            < 0
        ):
            raise ValueError("context budgets cannot be negative")
        if history_cap_tokens is not None and history_cap_tokens < 1:
            raise ValueError("history cap must be positive")

        sections = [
            ContextSourceBudget(
                source="system_tools",
                policy="required",
                estimated_tokens=input_overhead_tokens,
            )
        ]
        fixed_tokens = input_overhead_tokens
        for source, values in fixed_sections:
            tokens = estimate_context_tokens(*values)
            sections.append(
                ContextSourceBudget(
                    source=source,
                    policy="required",
                    estimated_tokens=tokens,
                )
            )
            fixed_tokens += tokens
        image_tokens = image_count * image_estimate_tokens
        sections.extend(
            (
                ContextSourceBudget(
                    source="images",
                    policy="bounded_reserve",
                    estimated_tokens=image_tokens,
                ),
                ContextSourceBudget(
                    source="evidence_reserve",
                    policy="bounded_reserve",
                    estimated_tokens=evidence_reserve_tokens,
                ),
            )
        )
        fixed_tokens += image_tokens + evidence_reserve_tokens
        history_tokens = estimate_context_tokens(*(item.text for item in history))
        summary_tokens = estimate_context_tokens(session_summary)
        sections.extend(
            (
                ContextSourceBudget(
                    source="history",
                    policy="compressible",
                    estimated_tokens=history_tokens,
                ),
                ContextSourceBudget(
                    source="history_summary",
                    policy="compressible",
                    estimated_tokens=summary_tokens,
                ),
            )
        )
        history_total = history_tokens + summary_tokens
        hard_stop_tokens = min(
            model_context_tokens - output_reserve_tokens,
            int(model_context_tokens * hard_stop_ratio),
        )
        soft_trigger_tokens = min(
            int(model_context_tokens * trigger_ratio),
            hard_stop_tokens - 1,
        )
        target_tokens = min(
            soft_trigger_tokens,
            int(model_context_tokens * (trigger_ratio - reserve_ratio)),
        )
        if not model_call_required:
            soft_trigger_tokens = model_context_tokens - 1
            hard_stop_tokens = model_context_tokens
            target_tokens = soft_trigger_tokens
        elif soft_trigger_tokens <= 0 or hard_stop_tokens <= 1 or target_tokens <= 0:
            raise ContextSnapshotError("CONTEXT_OUTPUT_RESERVE_EXCEEDS_WINDOW")
        if model_call_required and fixed_tokens > hard_stop_tokens:
            raise ContextSnapshotError("CONTEXT_REQUIRED_INPUT_EXCEEDS_WINDOW")
        estimated_before = fixed_tokens + history_total
        window_compression_required = model_call_required and estimated_before > soft_trigger_tokens
        effective_limit_tokens = (
            (hard_stop_tokens if fixed_tokens > soft_trigger_tokens else soft_trigger_tokens)
            if model_call_required
            else hard_stop_tokens
        )
        available = (
            (
                target_tokens
                if window_compression_required and fixed_tokens <= target_tokens
                else effective_limit_tokens
            )
            if model_call_required
            else model_context_tokens
        ) - fixed_tokens
        history_budget = (
            min(
                history_total,
                max(0, available),
                history_cap_tokens if history_cap_tokens is not None else history_total,
            )
            if model_call_required
            else history_total
        )
        compression_required = model_call_required and (
            window_compression_required or history_total > history_budget
        )
        source_payload = {
            "history": [item.model_dump(mode="json") for item in history],
            "session_summary": session_summary,
        }
        source_hash = hashlib.sha256(
            json.dumps(
                source_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        source_message_ids = tuple(
            item.stable_id or _derived_message_id(index=index, role=item.role, text=item.text)
            for index, item in enumerate(history)
        )
        summary_lineage_hashes = (
            (hashlib.sha256(session_summary.encode("utf-8")).hexdigest(),)
            if session_summary
            else ()
        )
        return ContextWindowDraft(
            model_context_tokens=model_context_tokens,
            soft_trigger_tokens=soft_trigger_tokens,
            hard_stop_tokens=hard_stop_tokens,
            effective_limit_tokens=effective_limit_tokens,
            target_tokens=target_tokens,
            output_reserve_tokens=output_reserve_tokens,
            history_budget_tokens=history_budget,
            estimated_tokens_before=estimated_before,
            history_tokens_before=history_total,
            history_message_count=len(history),
            source_hash=source_hash,
            source_history=history,
            source_message_ids=source_message_ids,
            summary_lineage_hashes=summary_lineage_hashes,
            unresolved_item_ids=unresolved_item_ids,
            sections=tuple(sections),
            compression_required=compression_required,
            model_call_required=model_call_required,
        )

    def compress_extractively(
        self,
        history: tuple[ConversationHistoryMessage, ...],
        *,
        token_budget: int,
        existing_summary: str = "",
    ) -> tuple[tuple[ConversationHistoryMessage, ...], str]:
        """Keep recent turns verbatim and summarize older turns with exact excerpts."""

        if token_budget < 1:
            return (), ""
        retained: list[ConversationHistoryMessage] = []
        retained_tokens = 0
        retained_budget = token_budget * 3 // 5
        for message in reversed(history):
            if len(retained) >= 6:
                break
            message_tokens = estimate_context_tokens(message.text)
            if retained_tokens + message_tokens > retained_budget:
                break
            retained.append(message)
            retained_tokens += message_tokens
        retained.reverse()
        older = history[: len(history) - len(retained)]
        remaining = max(0, token_budget - retained_tokens)
        if not older and estimate_context_tokens(existing_summary) <= remaining:
            return tuple(retained), existing_summary

        candidates: list[tuple[int, int, str]] = []
        seen_excerpts: set[str] = set()
        if existing_summary:
            candidates.append((2, -1, f"[既有摘要, 待核验]\n{existing_summary.strip()}"))
        for message_index, message in enumerate(older):
            role = "用户原文" if message.role == "user" else "历史助手内容, 待核验"
            for segment in _SEGMENT.findall(message.text):
                excerpt = segment.strip()
                if not excerpt or excerpt in seen_excerpts:
                    continue
                seen_excerpts.add(excerpt)
                priority = (
                    0
                    if message.role == "user"
                    and (
                        _CLINICAL_CRITICAL.search(excerpt)
                        or _USER_REQUIREMENT_CRITICAL.search(excerpt)
                    )
                    else 1
                    if message.role == "user"
                    else 2
                )
                candidates.append((priority, message_index, f"[{role}] {excerpt}"))
        selected: list[tuple[int, str]] = []
        used = 0
        for _priority, order, excerpt in sorted(candidates, key=lambda item: (item[0], -item[1])):
            excerpt_tokens = estimate_context_tokens(excerpt)
            if used + excerpt_tokens > remaining:
                excerpt = _truncate_exact_excerpt(excerpt, remaining - used)
                excerpt_tokens = estimate_context_tokens(excerpt)
                if not excerpt:
                    continue
            selected.append((order, excerpt))
            used += excerpt_tokens
        selected.sort(key=lambda item: item[0])
        summary = "\n".join(item[1] for item in selected)
        return tuple(retained), summary

    def finalize(
        self,
        draft: ContextWindowDraft,
        *,
        history: tuple[ConversationHistoryMessage, ...],
        session_summary: str,
        strategy: Literal[
            "none",
            "agentscope-medical-summary-v1",
            "deterministic-extractive-v1",
        ],
    ) -> ContextProjectionManifestV2:
        after_history_tokens = estimate_context_tokens(
            session_summary,
            *(item.text for item in history),
        )
        fixed_tokens = draft.estimated_tokens_before - draft.history_tokens_before
        estimated_after = fixed_tokens + after_history_tokens
        if draft.model_call_required and estimated_after > draft.effective_limit_tokens:
            raise ContextSnapshotError("CONTEXT_COMPRESSION_INSUFFICIENT")
        compressed = after_history_tokens < draft.history_tokens_before
        retained_ids = _retained_source_ids(draft, history)
        retained_id_set = set(retained_ids)
        omitted_ids = tuple(
            item for item in draft.source_message_ids if item not in retained_id_set
        )
        summary_lineage_hashes = list(draft.summary_lineage_hashes)
        if session_summary:
            projected_summary_hash = hashlib.sha256(session_summary.encode("utf-8")).hexdigest()
            if projected_summary_hash not in summary_lineage_hashes:
                summary_lineage_hashes.append(projected_summary_hash)
        return ContextProjectionManifestV2(
            model_context_tokens=draft.model_context_tokens,
            projection_mode=(
                "model_call" if draft.model_call_required else "deterministic_short_circuit"
            ),
            soft_trigger_tokens=draft.soft_trigger_tokens,
            hard_stop_tokens=draft.hard_stop_tokens,
            effective_limit_tokens=draft.effective_limit_tokens,
            target_tokens=draft.target_tokens,
            output_reserve_tokens=draft.output_reserve_tokens,
            estimated_tokens_before=draft.estimated_tokens_before,
            estimated_tokens_after=estimated_after,
            history_budget_tokens=draft.history_budget_tokens,
            history_message_count=draft.history_message_count,
            retained_history_message_count=len(retained_ids),
            compression_state="compressed" if compressed else "not_needed",
            compression_strategy=(strategy if compressed else "none"),
            source_hash=draft.source_hash,
            source_message_ids=draft.source_message_ids,
            retained_message_ids=retained_ids,
            omitted_message_ids=omitted_ids,
            source_range_start_id=(
                draft.source_message_ids[0] if draft.source_message_ids else None
            ),
            source_range_end_id=(
                draft.source_message_ids[-1] if draft.source_message_ids else None
            ),
            summary_lineage_hashes=tuple(summary_lineage_hashes),
            unresolved_item_ids=draft.unresolved_item_ids,
            sections=draft.sections,
        )


def _derived_message_id(*, index: int, role: str, text: str) -> str:
    digest = hashlib.sha256(f"{role}\0{text}".encode()).hexdigest()[:24]
    return f"history:{index}:{digest}"


def _truncate_exact_excerpt(value: str, token_budget: int) -> str:
    if token_budget < 1:
        return ""
    selected: list[str] = []
    selected_bytes = 0
    for character in value:
        next_bytes = selected_bytes + len(character.encode())
        if (next_bytes + 2) // 3 > token_budget:
            break
        selected.append(character)
        selected_bytes = next_bytes
    return "".join(selected).strip()


def _retained_source_ids(
    draft: ContextWindowDraft,
    history: tuple[ConversationHistoryMessage, ...],
) -> tuple[str, ...]:
    remaining = list(zip(draft.source_history, draft.source_message_ids, strict=True))
    retained: list[str] = []
    for projected in history:
        match_index = next(
            (
                index
                for index, (source, source_id) in enumerate(remaining)
                if (
                    projected.stable_id == source_id
                    or (projected.role == source.role and projected.text == source.text)
                )
            ),
            None,
        )
        if match_index is None:
            continue
        _source, source_id = remaining.pop(match_index)
        retained.append(source_id)
    retained_set = set(retained)
    return tuple(source_id for source_id in draft.source_message_ids if source_id in retained_set)
