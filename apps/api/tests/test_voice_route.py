"""FastAPI Voice boundary tests without a live provider or runtime dependencies."""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from gerclaw_api.application import create_app
from gerclaw_api.auth import create_access_token
from gerclaw_api.modules.voice import VoiceProviderUnavailable
from tests.conftest import make_settings


class _RateLimiter:
    async def check(self, **_kwargs: str) -> None:
        return None


class _Voice:
    default_voice = "冰糖"

    async def transcribe(self, audio_data: bytes, **_kwargs: str) -> str:
        assert audio_data == b"audio"
        return "测试转写"

    async def synthesize(self, _text: str, **_kwargs: str) -> AsyncGenerator[bytes, None]:
        yield b"\x01\x00"


class _UnavailableVoice(_Voice):
    async def synthesize(self, _text: str, **_kwargs: str) -> AsyncGenerator[bytes, None]:
        raise VoiceProviderUnavailable("test")
        yield b""  # pragma: no cover - preserves the async-generator contract


@pytest.mark.asyncio
async def test_voice_routes_require_scope_and_return_bounded_asr_and_pcm16() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    app.state.voice_module = _Voice()
    token = create_access_token(
        settings,
        actor_id="usr_patient_voice0001",
        tenant_id="tenant_public0001",
        scopes={"voice:use"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        asr = await client.post(
            "/api/v1/voice/asr",
            json={"audio": base64.b64encode(b"audio").decode(), "format": "wav"},
        )
        tts = await client.post("/api/v1/voice/tts", json={"text": "请慢一点朗读"})

    assert asr.status_code == 200
    assert asr.json() == {"text": "测试转写"}
    assert tts.status_code == 200
    assert tts.content == b"\x01\x00"
    assert tts.headers["content-type"].startswith("audio/L16")


@pytest.mark.asyncio
async def test_voice_routes_reject_missing_scope_and_invalid_audio() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    app.state.voice_module = _Voice()
    token = create_access_token(
        settings,
        actor_id="usr_patient_voice0001",
        tenant_id="tenant_public0001",
        scopes={"chat:write"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        forbidden = await client.post("/api/v1/voice/tts", json={"text": "测试"})

    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_voice_tts_projects_a_first_packet_provider_failure_before_headers() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    app.state.voice_module = _UnavailableVoice()
    token = create_access_token(
        settings,
        actor_id="usr_patient_voice0001",
        tenant_id="tenant_public0001",
        scopes={"voice:use"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        response = await client.post("/api/v1/voice/tts", json={"text": "测试"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VOICE_TTS_UNAVAILABLE"
