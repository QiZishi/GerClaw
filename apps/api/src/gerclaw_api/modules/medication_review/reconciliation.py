# ruff: noqa: RUF001
"""Bounded, non-clinical medication-list reconciliation.

This identifies only entries that are exactly equal after Unicode/whitespace
normalization. It never maps synonyms, infers a medicine, parses a dose, or
makes a DDI/Beers/dose decision.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict

from gerclaw_api.modules.medication_review.models import (
    MedicationDuplicateCandidate,
    MedicationListEntry,
    MedicationReconciliationRead,
)

MEDICATION_RECONCILIATION_VERSION = "medication-reconciliation-v1"
MAX_MEDICATION_ENTRIES = 50
RECONCILIATION_NOTICE = (
    "此处只核对完全相同的录入条目，不能判断药物相互作用、禁忌、重复成分或剂量是否合适；"
    "请由医生或药师核对。"
)


class MedicationReconciliationInputError(ValueError):
    """The caller must simplify the medication list before it can be displayed safely."""


def reconcile_medication_list(
    *, intake_id: uuid.UUID, medication_list: str
) -> MedicationReconciliationRead:
    """Return a deterministic owner-visible input-quality preview."""

    rows = _split_entries(medication_list)
    if len(rows) > MAX_MEDICATION_ENTRIES:
        raise MedicationReconciliationInputError("medication list has too many entries")

    entries = tuple(
        MedicationListEntry(position=position, text=text)
        for position, text in enumerate(rows, start=1)
    )
    positions_by_key: defaultdict[str, list[int]] = defaultdict(list)
    label_by_key: dict[str, str] = {}
    for entry in entries:
        key = _exact_entry_key(entry.text)
        positions_by_key[key].append(entry.position)
        label_by_key.setdefault(key, entry.text)
    duplicates = tuple(
        MedicationDuplicateCandidate(text=label_by_key[key], positions=tuple(positions))
        for key, positions in positions_by_key.items()
        if len(positions) > 1
    )
    return MedicationReconciliationRead(
        intake_id=intake_id,
        version=MEDICATION_RECONCILIATION_VERSION,
        has_medication_list=bool(rows),
        entries=entries,
        exact_duplicate_candidates=duplicates,
        notice=RECONCILIATION_NOTICE,
    )


def _split_entries(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    return tuple(
        collapsed
        for part in re.split(r"[\n；;]", normalized)
        if (collapsed := " ".join(part.split()))
    )


def _exact_entry_key(value: str) -> str:
    """Use no clinical vocabulary or fuzzy matching at this safety boundary."""

    return "".join(value.casefold().split())
