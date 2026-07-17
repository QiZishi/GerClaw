# ruff: noqa: RUF001
"""FastAPI Voice boundary tests without a live provider or runtime dependencies."""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from gerclaw_api.application import create_app
from gerclaw_api.auth import create_access_token
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.voice import VoiceProviderUnavailable
from tests.conftest import make_settings


class _RateLimiter:
    async def check(self, **_kwargs: str) -> None:
        return None


class _Voice:
    default_voice = "冰糖"

    def __init__(self) -> None:
        self.tts_requests: list[tuple[str, dict[str, object]]] = []

    async def transcribe(self, audio_data: bytes, **_kwargs: str) -> str:
        assert audio_data == b"audio"
        return "测试转写"

    async def synthesize(self, text: str, **kwargs: str) -> AsyncGenerator[bytes, None]:
        self.tts_requests.append((text, kwargs))
        yield b"\x01\x00"


class _UnavailableVoice(_Voice):
    async def synthesize(self, text: str, **kwargs: str) -> AsyncGenerator[bytes, None]:
        self.tts_requests.append((text, kwargs))
        raise VoiceProviderUnavailable("test")
        yield b""  # pragma: no cover - preserves the async-generator contract


class _UnavailableASRVoice(_Voice):
    async def transcribe(self, audio_data: bytes, **_kwargs: str) -> str:
        assert audio_data == b"audio"
        raise VoiceProviderUnavailable("test")


class _EgressSession:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.commit_count = 0

    def add(self, event: object) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1


def _with_egress_session(app: object, egress_session: _EgressSession) -> None:
    async def dependency() -> _EgressSession:
        yield egress_session

    app.dependency_overrides[get_database_session] = dependency  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_voice_routes_require_scope_and_return_bounded_asr_and_pcm16() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    voice = _Voice()
    app.state.voice_module = voice
    egress_session = _EgressSession()
    _with_egress_session(app, egress_session)
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
        tts = await client.post(
            "/api/v1/voice/tts",
            json={
                "text": "患者姓名：李雷，电话 13800138000，请慢一点朗读",
                "style": "name: John Smith, token=provider-secret 温和朗读",
            },
        )

    assert asr.status_code == 200
    assert asr.json() == {"schema_version": "voice-asr-response-v1", "text": "测试转写"}
    assert asr.headers["x-gerclaw-voice-contract"] == "voice-asr-response-v1"
    assert tts.status_code == 200
    assert tts.content == b"\x01\x00"
    assert tts.headers["content-type"].startswith("audio/L16")
    assert tts.headers["x-gerclaw-voice-contract"] == "voice-tts-pcm16-v1"
    assert voice.tts_requests == [
        (
            "您，电话 [PHONE]，请慢一点朗读",
            {"voice": "冰糖", "style": "您, token=[REDACTED] 温和朗读"},
        )
    ]
    assert len(egress_session.events) == 2
    asr_event, tts_event = egress_session.events
    assert asr_event.purpose == "external_asr_audio"
    assert asr_event.processor == "mimo_asr"
    assert asr_event.policy_version == "audio-egress-v1"
    assert asr_event.outcome == "succeeded"
    assert asr_event.findings == []
    assert tts_event.purpose == "external_tts"
    assert tts_event.processor == "mimo_tts"
    assert tts_event.policy_version == "1.1.0"
    assert tts_event.outcome == "succeeded"
    assert tts_event.findings == [
        {"field": "text", "category": "person_name", "count": 1},
        {"field": "text", "category": "phone", "count": 1},
        {"field": "style", "category": "credential", "count": 1},
        {"field": "style", "category": "person_name", "count": 1},
    ]
    assert egress_session.commit_count == 4


@pytest.mark.asyncio
async def test_voice_routes_reject_missing_scope_and_invalid_audio() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    voice = _Voice()
    app.state.voice_module = voice
    egress_session = _EgressSession()
    _with_egress_session(app, egress_session)
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

    valid_token = create_access_token(
        settings,
        actor_id="usr_patient_voice0001",
        tenant_id="tenant_public0001",
        scopes={"voice:use"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {valid_token}"},
    ) as client:
        invalid_audio = await client.post(
            "/api/v1/voice/asr", json={"audio": "not-base64", "format": "wav"}
        )

    assert forbidden.status_code == 403
    assert invalid_audio.status_code == 422
    assert egress_session.events == []
    assert voice.tts_requests == []


@pytest.mark.asyncio
async def test_voice_tts_projects_a_first_packet_provider_failure_before_headers() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    app.state.voice_module = _UnavailableVoice()
    egress_session = _EgressSession()
    _with_egress_session(app, egress_session)
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
    assert len(egress_session.events) == 1
    assert egress_session.events[0].outcome == "failed"
    assert egress_session.commit_count == 2


@pytest.mark.asyncio
async def test_voice_asr_records_failed_audio_egress_without_audio_or_transcript() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    app.state.voice_module = _UnavailableASRVoice()
    egress_session = _EgressSession()
    _with_egress_session(app, egress_session)
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
        response = await client.post(
            "/api/v1/voice/asr",
            json={"audio": base64.b64encode(b"audio").decode(), "format": "wav"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VOICE_ASR_UNAVAILABLE"
    assert len(egress_session.events) == 1
    event = egress_session.events[0]
    assert event.purpose == "external_asr_audio"
    assert event.processor == "mimo_asr"
    assert event.policy_version == "audio-egress-v1"
    assert event.outcome == "failed"
    assert event.findings == []
    assert egress_session.commit_count == 2
