"""Strict public consent contracts with no patient health data."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ResourceScope = Literal[
    "health_profile_read",
    "cga_report_read",
    "prescription_draft_review",
    "medication_review_read",
]


class PatientAccessGrantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    resource_scopes: tuple[ResourceScope, ...] = Field(min_length=1, max_length=4)
    expires_at: datetime

    @field_validator("resource_scopes")
    @classmethod
    def resource_scopes_must_be_unique(
        cls, value: tuple[ResourceScope, ...]
    ) -> tuple[ResourceScope, ...]:
        if len(set(value)) != len(value):
            raise ValueError("resource_scopes must not contain duplicates")
        return value


class PatientAccessGrantRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class PatientAccessGrantRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    doctor_actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    resource_scope: ResourceScope
    status: Literal["active", "revoked", "expired"]
    expires_at: datetime
    revision: int = Field(ge=1)
    granted_at: datetime
    revoked_at: datetime | None = None


class PatientAccessGrantListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PatientAccessGrantRead] = Field(default_factory=list, max_length=100)


class DoctorPatientGrantScopeRead(BaseModel):
    """One currently effective projection a patient has granted to this doctor."""

    model_config = ConfigDict(extra="forbid")

    resource_scope: ResourceScope
    expires_at: datetime


class DoctorPatientAccessRead(BaseModel):
    """Deliberately minimal patient directory entry for an authorized doctor."""

    model_config = ConfigDict(extra="forbid")

    patient_actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    grants: tuple[DoctorPatientGrantScopeRead, ...] = Field(min_length=1, max_length=4)


class DoctorPatientAccessListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DoctorPatientAccessRead] = Field(default_factory=list, max_length=100)
