"""Authenticated ASR and streaming PCM16 TTS API boundary."""

from __future__ import annotations

import base64
import binascii
from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_voice_use
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.privacy_redaction.policy import redact_external_tts_text
from gerclaw_api.modules.voice import (
    MiMoVoiceModule,
    VoiceProviderInvalidResponse,
    VoiceProviderUnavailable,
)
from gerclaw_api.modules.voice.models import (
    VOICE_ASR_RESPONSE_SCHEMA_VERSION,
    VOICE_TTS_MEDIA_CONTRACT_VERSION,
    VoiceASRRequest,
    VoiceASRResponse,
    VoiceTTSRequest,
)
from gerclaw_api.repositories.provider_egress import SqlAlchemyProviderEgressRepository
from gerclaw_api.services.rate_limit import RateLimiter

router = APIRouter(prefix="/voice", tags=["voice"])
VoiceIdentity = Annotated[AuthContext, Depends(require_voice_use)]
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
_MAX_ASR_AUDIO_BYTES = 7 * 1024 * 1024


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _module(request: Request) -> MiMoVoiceModule:
    module = getattr(request.app.state, "voice_module", None)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "VOICE_UNAVAILABLE", "message": "voice service is unavailable"},
        )
    return cast(MiMoVoiceModule, module)


VoiceModuleDependency = Annotated[MiMoVoiceModule, Depends(_module)]


def _decode_audio(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "VOICE_AUDIO_INVALID"},
        ) from error
    if not decoded or len(decoded) > _MAX_ASR_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "VOICE_AUDIO_TOO_LARGE"},
        )
    return decoded


async def _prepend_first_chunk(
    stream: AsyncGenerator[bytes, None], first_chunk: bytes
) -> AsyncGenerator[bytes, None]:
    """Keep the verified first PCM16 chunk while releasing a cancelled provider stream."""

    try:
        yield first_chunk
        async for chunk in stream:
            yield chunk
    finally:
        await stream.aclose()


@router.post("/asr", response_model=VoiceASRResponse)
async def transcribe(
    payload: VoiceASRRequest,
    request: Request,
    http_response: Response,
    identity: VoiceIdentity,
    session: SessionDependency,
    module: VoiceModuleDependency,
) -> VoiceASRResponse:
    """Recognise one bounded WAV/MP3 payload without persisting it or its text."""

    await _enforce_rate_limit(request, identity)
    audio = _decode_audio(payload.audio)
    egress = SqlAlchemyProviderEgressRepository(session)
    event = await egress.record_prepared_asr_audio(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    await session.commit()
    try:
        result = VoiceASRResponse(
            text=await module.transcribe(audio, audio_format=payload.format)
        )
    except VoiceProviderUnavailable as error:
        await egress.set_outcome(event, outcome="failed")
        await session.commit()
        raise HTTPException(status_code=503, detail={"code": "VOICE_ASR_UNAVAILABLE"}) from error
    except VoiceProviderInvalidResponse as error:
        await egress.set_outcome(event, outcome="failed")
        await session.commit()
        raise HTTPException(
            status_code=502, detail={"code": "VOICE_ASR_INVALID_RESPONSE"}
        ) from error
    await egress.set_outcome(event, outcome="succeeded")
    await session.commit()
    http_response.headers["X-GerClaw-Voice-Contract"] = VOICE_ASR_RESPONSE_SCHEMA_VERSION
    return result


@router.post("/tts")
async def synthesize(
    payload: VoiceTTSRequest,
    request: Request,
    identity: VoiceIdentity,
    session: SessionDependency,
    module: VoiceModuleDependency,
) -> StreamingResponse:
    """Stream 24 kHz mono PCM16LE; clients own playback, pause and cancellation."""

    await _enforce_rate_limit(request, identity)
    voice = payload.voice or module.default_voice
    text_decision = redact_external_tts_text(payload.text.strip())
    style_decision = redact_external_tts_text(payload.style) if payload.style is not None else None
    egress = SqlAlchemyProviderEgressRepository(session)
    event = await egress.record_prepared(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        processor="mimo_tts",
        decisions={
            "text": text_decision,
            **({"style": style_decision} if style_decision is not None else {}),
        },
    )
    await session.commit()
    stream = module.synthesize(
        text_decision.text,
        voice=voice,
        style=style_decision.text if style_decision is not None else None,
    )
    try:
        first_chunk = await anext(stream)
    except VoiceProviderUnavailable as error:
        await egress.set_outcome(event, outcome="failed")
        await session.commit()
        raise HTTPException(status_code=503, detail={"code": "VOICE_TTS_UNAVAILABLE"}) from error
    except VoiceProviderInvalidResponse as error:
        await egress.set_outcome(event, outcome="failed")
        await session.commit()
        raise HTTPException(
            status_code=502, detail={"code": "VOICE_TTS_INVALID_RESPONSE"}
        ) from error
    except StopAsyncIteration as error:
        await egress.set_outcome(event, outcome="failed")
        await session.commit()
        raise HTTPException(
            status_code=502, detail={"code": "VOICE_TTS_INVALID_RESPONSE"}
        ) from error
    await egress.set_outcome(event, outcome="succeeded")
    await session.commit()
    return StreamingResponse(
        _prepend_first_chunk(stream, first_chunk),
        media_type="audio/L16;rate=24000;channels=1",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-GerClaw-Voice-Contract": VOICE_TTS_MEDIA_CONTRACT_VERSION,
        },
    )
