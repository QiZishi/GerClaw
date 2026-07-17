"""Immutable contracts for the workflows that may enter the Runtime Harness."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.runtime.models import VERSION, DataClass, NetworkAccess, RiskLevel

STRICT = ConfigDict(extra="forbid", frozen=True)


class WorkflowId(StrEnum):
    """Only server-owned workflows may be selected at the chat boundary."""

    STANDARD = "standard"
    CGA = "cga"
    COMPANION = "companion"


class WorkflowDefinition(BaseModel):
    """Versioned policy for one executable workflow, not a browser-provided hint."""

    model_config = STRICT

    workflow_id: WorkflowId
    version: str = Field(pattern=VERSION)
    owner_module: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    description: str = Field(min_length=8, max_length=300)
    risk_level: RiskLevel
    network_access: NetworkAccess
    data_classes: frozenset[DataClass] = Field(min_length=1, max_length=6)
    accepts_skills: bool
    accepts_uploaded_files: bool
    search_enabled: bool

    @model_validator(mode="after")
    def keep_companion_isolated(self) -> WorkflowDefinition:
        if self.workflow_id is WorkflowId.COMPANION and (
            self.accepts_skills or self.accepts_uploaded_files or self.search_enabled
        ):
            raise ValueError("companion workflow cannot enable Skills, files, or search")
        return self


class WorkflowContextError(ValueError):
    """A caller proposed context that the server-owned workflow does not allow."""

