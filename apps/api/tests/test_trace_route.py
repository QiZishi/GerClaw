"""Trace read ownership rules that must not regress to tenant-only access."""

from __future__ import annotations

import pytest

from gerclaw_api.api.routes.traces import _ensure_trace_read_access
from gerclaw_api.auth import AuthContext
from gerclaw_api.services.trace_service import TraceNotFoundError


def _identity(*, actor_id: str, role: str, account_role: str) -> AuthContext:
    return AuthContext(
        actor_id=actor_id,
        tenant_id="tenant_public0001",
        role=role,
        account_role=account_role,
        scopes=frozenset({"trace:read"}),
    )


def test_trace_read_is_limited_to_the_owner_for_patient_doctor_and_guest() -> None:
    for role, account_role in (("patient", "patient"), ("doctor", "doctor"), ("guest", "guest")):
        with pytest.raises(TraceNotFoundError):
            _ensure_trace_read_access(
                _identity(
                    actor_id="usr_account_0123456789abcdef0123456789abcdef"
                    if role != "guest"
                    else "usr_guest_0123456789abcdef0123456789abcdef",
                    role=role,
                    account_role=account_role,
                ),
                "usr_account_fedcba9876543210fedcba9876543210",
                "trace_owner_scope_0001",
            )


def test_trace_read_allows_owner_and_explicit_administrator() -> None:
    owner = _identity(
        actor_id="usr_account_0123456789abcdef0123456789abcdef",
        role="patient",
        account_role="patient",
    )
    _ensure_trace_read_access(owner, owner.actor_id, "trace_owner_scope_0001")

    administrator = _identity(
        actor_id="usr_account_fedcba9876543210fedcba9876543210",
        role="admin",
        account_role="admin",
    )
    _ensure_trace_read_access(
        administrator,
        "usr_account_0123456789abcdef0123456789abcdef",
        "trace_owner_scope_0001",
    )
