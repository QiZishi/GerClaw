"""Pure storage projections shared by online and offline Skill mutation paths."""

from __future__ import annotations

import hashlib
from typing import Any

from gerclaw_api.database.models import SkillDefinitionRecord


def skill_content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def skill_name_fingerprint(value: str) -> str:
    normalized = " ".join(value.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def skill_record_snapshot(record: SkillDefinitionRecord) -> dict[str, Any]:
    return {
        "skill_id": record.skill_id,
        "name": record.name,
        "description": record.description,
        "version": record.version,
        "category": record.category,
        "origin": record.origin,
        "tool_names": record.tool_names,
        "source_markdown": record.source_markdown,
        "content_hash": record.content_hash,
        "enabled": record.enabled,
        "revision": record.revision,
    }
