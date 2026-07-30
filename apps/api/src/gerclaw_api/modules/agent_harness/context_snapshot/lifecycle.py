"""Pre-model context inventory, early overflow detection, and safe projection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from gerclaw_api.modules.agent_harness.context_snapshot.models import (
    ContextProjectionManifest,
    ContextSnapshotError,
    ContextSourceBudget,
    ConversationHistoryMessage,
)

_SEGMENT = re.compile(r"[^。！？!?\n]+(?:[。！？!?]+|\n+|$)")  # noqa: RUF001
_CLINICAL_CRITICAL = re.compile(
    r"过敏|药|剂量|停用|血压|血糖|心率|胸痛|呼吸困难|意识|偏瘫|"
    r"出血|自伤|跌倒|诊断|检查|化验|手术|住院|急诊|否认|没有|不"
)


def estimate_context_tokens(*values: str) -> int:
    """Conservative dependency-free UTF-8 estimate shared by projection."""

    return sum(max(1, (len(value.encode("utf-8")) + 2) // 3) for value in values if value)


@dataclass(frozen=True, slots=True)
class ContextWindowDraft:
    """Pre-compression decision based on every known model-visible source."""

    model_context_tokens: int
    trigger_tokens: int
    target_tokens: int
    output_reserve_tokens: int
    history_budget_tokens: int
    estimated_tokens_before: int
    history_tokens_before: int
    history_message_count: int
    source_hash: str
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
        fixed_sections: tuple[tuple[str, tuple[str, ...]], ...],
        model_context_tokens: int,
        trigger_ratio: float,
        reserve_ratio: float,
        output_reserve_tokens: int,
        input_overhead_tokens: int,
        image_count: int,
        image_estimate_tokens: int,
        evidence_reserve_tokens: int,
        history_cap_tokens: int | None = None,
        model_call_required: bool = True,
    ) -> ContextWindowDraft:
        if model_context_tokens <= 0:
            raise ValueError("model context size must be positive")
        if not 0 < reserve_ratio < trigger_ratio < 1:
            raise ValueError("context ratios must satisfy 0 < reserve < trigger < 1")
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
                    source=source,  # type: ignore[arg-type]
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
        trigger_tokens = min(
            model_context_tokens - output_reserve_tokens,
            int(model_context_tokens * trigger_ratio),
        )
        target_tokens = min(
            trigger_tokens,
            int(model_context_tokens * (trigger_ratio - reserve_ratio)),
        )
        if not model_call_required:
            trigger_tokens = model_context_tokens
            target_tokens = model_context_tokens
        elif trigger_tokens <= 0 or target_tokens <= 0:
            raise ContextSnapshotError("CONTEXT_OUTPUT_RESERVE_EXCEEDS_WINDOW")
        if model_call_required and fixed_tokens > trigger_tokens:
            raise ContextSnapshotError("CONTEXT_REQUIRED_INPUT_EXCEEDS_WINDOW")
        estimated_before = fixed_tokens + history_total
        window_compression_required = model_call_required and estimated_before > trigger_tokens
        available = (
            target_tokens if window_compression_required else trigger_tokens
        ) - fixed_tokens
        if model_call_required and available < 1 and history_total:
            raise ContextSnapshotError("CONTEXT_REQUIRED_INPUT_EXCEEDS_WINDOW")
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
        return ContextWindowDraft(
            model_context_tokens=model_context_tokens,
            trigger_tokens=trigger_tokens,
            target_tokens=target_tokens,
            output_reserve_tokens=output_reserve_tokens,
            history_budget_tokens=history_budget,
            estimated_tokens_before=estimated_before,
            history_tokens_before=history_total,
            history_message_count=len(history),
            source_hash=source_hash,
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
        if existing_summary:
            candidates.append((2, -1, f"[既有摘要, 待核验]\n{existing_summary.strip()}"))
        for message_index, message in enumerate(older):
            role = "用户原文" if message.role == "user" else "历史助手内容, 待核验"
            for segment in _SEGMENT.findall(message.text):
                excerpt = segment.strip()
                if not excerpt:
                    continue
                priority = (
                    0
                    if message.role == "user" and _CLINICAL_CRITICAL.search(excerpt)
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
        strategy: str,
    ) -> ContextProjectionManifest:
        after_history_tokens = estimate_context_tokens(
            session_summary,
            *(item.text for item in history),
        )
        fixed_tokens = draft.estimated_tokens_before - draft.history_tokens_before
        estimated_after = fixed_tokens + after_history_tokens
        if draft.model_call_required and estimated_after > draft.trigger_tokens:
            raise ContextSnapshotError("CONTEXT_COMPRESSION_INSUFFICIENT")
        compressed = after_history_tokens < draft.history_tokens_before
        return ContextProjectionManifest(
            model_context_tokens=draft.model_context_tokens,
            projection_mode=(
                "model_call" if draft.model_call_required else "deterministic_short_circuit"
            ),
            trigger_tokens=draft.trigger_tokens,
            target_tokens=draft.target_tokens,
            output_reserve_tokens=draft.output_reserve_tokens,
            estimated_tokens_before=draft.estimated_tokens_before,
            estimated_tokens_after=estimated_after,
            history_budget_tokens=draft.history_budget_tokens,
            history_message_count=draft.history_message_count,
            retained_history_message_count=len(history),
            compression_state="compressed" if compressed else "not_needed",
            compression_strategy=(
                strategy if compressed else "none"  # type: ignore[arg-type]
            ),
            source_hash=draft.source_hash,
            sections=draft.sections,
        )
