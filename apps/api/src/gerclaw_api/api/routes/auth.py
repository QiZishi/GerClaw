"""Pseudonymous visitor bootstrap for login-free product access."""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.auth import create_access_token
from gerclaw_api.services.rate_limit import RateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])

_GUEST_SCOPES = {
    "approval:read",
    "approval:write",
    "chat:read",
    "chat:write",
    "document:read",
    "document:write",
    "cga:read",
    "cga:write",
    "clinical_intake:read",
    "clinical_intake:write",
    "feedback:write",
    "memory:read",
    "memory:write",
    "rag:read",
    "search:read",
    "skill:execute",
    "skill:read",
    "skill:write",
    "trace:read",
    "trace:write",
}
_VISITOR_ID = re.compile(r"^[a-f0-9]{32}$")
_VISITOR_SIGNATURE = re.compile(r"^[a-f0-9]{64}$")


class GuestTokenRead(BaseModel):
    """Short-lived bearer credential returned only to the trusted BFF."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=32)
    token_type: str = "bearer"
    expires_in: int = Field(ge=300, le=86_400)
    actor_id: str = Field(pattern=r"^usr_guest_[a-f0-9]{32}$")


@router.post("/guest", response_model=GuestTokenRead)
async def issue_guest_token(request: Request) -> GuestTokenRead:
    """Issue an opaque, least-privilege visitor identity after rate limiting."""

    settings = request.app.state.settings
    peer = request.client.host if request.client is not None else "unknown"
    visitor_id = request.headers.get("X-GerClaw-Visitor-ID", "")
    visitor_signature = request.headers.get("X-GerClaw-Visitor-Signature", "")
    signature_payload = f"gerclaw-guest-bootstrap:v1:{visitor_id}"
    identity_secret = settings.guest_identity_secret.get_secret_value().encode()
    expected_signature = hmac.new(
        identity_secret,
        signature_payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    has_valid_bff_identity = (
        _VISITOR_ID.fullmatch(visitor_id) is not None
        and _VISITOR_SIGNATURE.fullmatch(visitor_signature) is not None
        and hmac.compare_digest(visitor_signature, expected_signature)
    )
    rate_material = f"visitor:{visitor_id}" if has_valid_bff_identity else f"peer:{peer}"
    rate_identity = hmac.new(
        identity_secret,
        rate_material.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id="tenant_public0001", actor_id=f"auth_{rate_identity}")
    if has_valid_bff_identity:
        actor_material = f"gerclaw-guest-actor:v1:{visitor_id}"
        actor_suffix = hmac.new(
            identity_secret,
            actor_material.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
    else:
        actor_suffix = uuid.uuid4().hex
    actor_id = f"usr_guest_{actor_suffix}"
    token = create_access_token(
        settings,
        actor_id=actor_id,
        tenant_id="tenant_public0001",
        scopes=_GUEST_SCOPES,
        lifetime_seconds=settings.guest_token_ttl_seconds,
    )
    return GuestTokenRead(
        access_token=token,
        expires_in=settings.guest_token_ttl_seconds,
        actor_id=actor_id,
    )
