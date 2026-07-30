"""Deterministic projection of one persisted user message into ClinicalState."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from gerclaw_api.modules.agent_harness.clinical_state.contracts import (
    ClinicalFact,
    ClinicalState,
    ClinicalStateReducer,
    FactProvenance,
)

_AGE = re.compile(r"(?<!\d)(\d{1,3})\s*岁")
_NEGATIVE_ALLERGY = re.compile(r"(?:没有|无|否认)(?:已知)?(?:药物)?过敏")
_POSITIVE_ALLERGY = re.compile(r"(?:对.{1,20}过敏|药物过敏史(?:是|为|:).+)")
_MEDICATION_REPORT = re.compile(
    r"(?:正在|目前|现在)(?:吃|服用|使用)|现用药|当前用药(?:是|为|有|包括|:)"
    r"|服用.{0,30}(?:mg|g|毫克|片|粒|每日|每天)"
)
_SYMPTOM = re.compile(r"头晕|乏力|胸痛|呼吸困难|气短|晕厥|发热|咳嗽|疼痛|腹泻|呕吐|水肿|失眠|心悸")
_HISTORY = re.compile(r"(?:患有|确诊过|有).{0,30}(?:病史|高血压|糖尿病|冠心病|肾病|肝病)")
_TIMELINE = re.compile(r"(?:持续|已经|近|最近).{0,12}(?:天|周|月|年|小时)")


class UserMessageClinicalProjector:
    """Record explicit user text and code-owned red-flag matches without inference."""

    def __init__(
        self,
        reducer: ClinicalStateReducer,
    ) -> None:
        self._reducer = reducer

    def project(
        self,
        current: ClinicalState,
        *,
        message_id: uuid.UUID,
        message: str,
        observed_at: datetime,
        red_flag_codes: tuple[str, ...],
    ) -> ClinicalState:
        source_id = f"message:{message_id}"
        provenance = (
            FactProvenance(
                source_type="user",
                source_id=source_id,
                observed_at=observed_at,
            ),
        )
        message_fact_id = f"user_message:{message_id}"
        observations: list[ClinicalFact] = []
        if not any(fact.fact_id == message_fact_id for fact in current.facts):
            observations.append(
                ClinicalFact(
                    fact_id=message_fact_id,
                    category="chief_complaint",
                    value=message,
                    status="reported",
                    provenance=provenance,
                )
            )
        semantic_facts: list[tuple[str, str, object]] = []
        if age := _AGE.search(message):
            semantic_facts.append(
                ("demographic", "demographic:age_years", {"age_years": int(age.group(1))})
            )
        if _NEGATIVE_ALLERGY.search(message):
            semantic_facts.append(
                (
                    "negative_evidence",
                    "allergy:drug_status",
                    "用户明确否认药物过敏",
                )
            )
        elif _POSITIVE_ALLERGY.search(message):
            semantic_facts.append(("allergy", "allergy:drug_status", message))
        if _MEDICATION_REPORT.search(message):
            semantic_facts.append(("medication", "medication:current_list", message))
        if _SYMPTOM.search(message):
            semantic_facts.append(("symptom", f"{message_fact_id}:symptom", message))
        if _HISTORY.search(message):
            semantic_facts.append(("history", f"{message_fact_id}:history", message))
        if _TIMELINE.search(message):
            semantic_facts.append(("timeline", f"{message_fact_id}:timeline", message))
        for category, fact_id, value in semantic_facts:
            if any(
                fact.fact_id == fact_id
                and any(item.source_id == source_id for item in fact.provenance)
                for fact in current.facts
            ):
                continue
            observations.append(
                ClinicalFact.model_validate(
                    {
                        "fact_id": fact_id,
                        "category": category,
                        "value": value,
                        "status": "reported",
                        "provenance": provenance,
                    }
                )
            )
        for code in red_flag_codes:
            fact_id = f"red_flag:{code}"
            existing = next(
                (
                    fact
                    for fact in current.facts
                    if fact.fact_id == fact_id
                    and fact.category == "red_flag"
                    and fact.value == code
                ),
                None,
            )
            if existing is None:
                observations.append(
                    ClinicalFact(
                        fact_id=fact_id,
                        category="red_flag",
                        value=code,
                        status="reported",
                        provenance=provenance,
                    )
                )
        return self._reducer.reduce(current, tuple(observations))
