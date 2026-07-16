"""Authenticated ASR and streaming PCM16 TTS API boundary."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from gerclaw_api.auth import AuthContext, require_voice_use
from gerclaw_api.modules.voice import (
    MiMoVoiceModule,
    VoiceProviderInvalidResponse,
    VoiceProviderUnavailable,
)
from gerclaw_api.modules.voice.models import VoiceASRRequest, VoiceASRResponse, VoiceTTSRequest
from gerclaw_api.services.rate_limit import RateLimiter

router = APIRouter(prefix="/voice", tags=["voice"])
VoiceIdentity = Annotated[AuthContext, Depends(require_voice_use)]
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VOICE_AUDIO_INVALID"},
        ) from error
    if not decoded or len(decoded) > _MAX_ASR_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "VOICE_AUDIO_TOO_LARGE"},
        )
    return decoded


@router.post("/asr", response_model=VoiceASRResponse)
async def transcribe(
    payload: VoiceASRRequest,
    request: Request,
    identity: VoiceIdentity,
    module: VoiceModuleDependency,
) -> VoiceASRResponse:
    """Recognise one bounded WAV/MP3 payload without persisting it or its text."""

    await _enforce_rate_limit(request, identity)
    try:
        text = await module.transcribe(_decode_audio(payload.audio), audio_format=payload.format)
    except VoiceProviderUnavailable as error:
        raise HTTPException(status_code=503, detail={"code": "VOICE_ASR_UNAVAILABLE"}) from error
    except VoiceProviderInvalidResponse as error:
        raise HTTPException(
            status_code=502, detail={"code": "VOICE_ASR_INVALID_RESPONSE"}
        ) from error
    return VoiceASRResponse(text=text)


@router.post("/tts")
async def synthesize(
    payload: VoiceTTSRequest,
    request: Request,
    identity: VoiceIdentity,
    module: VoiceModuleDependency,
) -> StreamingResponse:
    """Stream 24 kHz mono PCM16LE; clients own playback, pause and cancellation."""

    await _enforce_rate_limit(request, identity)
    voice = payload.voice or module.default_voice
    try:
        stream = module.synthesize(payload.text.strip(), voice=voice, style=payload.style)
        return StreamingResponse(
            stream,
            media_type="audio/L16;rate=24000;channels=1",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    except VoiceProviderUnavailable as error:
        raise HTTPException(status_code=503, detail={"code": "VOICE_TTS_UNAVAILABLE"}) from error
    except VoiceProviderInvalidResponse as error:
        raise HTTPException(
            status_code=502, detail={"code": "VOICE_TTS_INVALID_RESPONSE"}
        ) from error
