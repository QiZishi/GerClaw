# ruff: noqa: RUF001
"""Offline SSE contract tests for the FastAPI Runtime voice adapter."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from gerclaw_api.modules.voice.module import (
    MiMoVoiceModule,
    VoiceProviderCapabilityUnavailable,
    VoiceProviderInvalidResponse,
)


def _sse(payloads: list[dict[str, object]]) -> str:
    return "".join(f"data: {json.dumps(payload)}\n\n" for payload in payloads) + "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_voice_module_parses_asr_and_pcm16_sse_without_retaining_payloads() -> None:
    pcm = b"\x01\x00\x02\x00"

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer test-key"
        if payload["model"] == "mimo-v2.5-asr":
            return httpx.Response(
                200,
                text=_sse(
                    [
                        {"choices": [{"delta": {"content": "您好"}}]},
                        {"choices": [{"delta": {"content": "，请说。"}}]},
                        {"choices": []},
                    ]
                ),
            )
        assert payload["audio"] == {"format": "pcm16", "voice": "冰糖"}
        return httpx.Response(
            200,
            text=_sse(
                [
                    {"choices": [{"delta": {"audio": {"data": base64.b64encode(pcm).decode()}}}]},
                    {"choices": []},
                ]
            ),
        )

    module = MiMoVoiceModule(
        asr_url="https://voice.test/v1",
        tts_url="https://voice.test/v1",
        api_key="test-key",
        auth_header="authorization",
        asr_model="mimo-v2.5-asr",
        tts_model="mimo-v2.5-tts",
        default_voice="冰糖",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await module.transcribe(b"audio", audio_format="wav") == "您好，请说。"
        assert [chunk async for chunk in module.synthesize("测试", voice="冰糖")] == [pcm]
    finally:
        await module.aclose()


@pytest.mark.asyncio
async def test_voice_capability_mismatch_fails_before_provider_egress() -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    module = MiMoVoiceModule(
        asr_url="https://voice.test/v1",
        tts_url="https://voice.test/v1",
        api_key="test-key",
        auth_header="authorization",
        asr_model="mimo-v2.5-asr",
        tts_model="mimo-v2.5-tts",
        default_voice="冰糖",
        timeout_seconds=2,
        supports_streaming_asr=False,
        supports_pcm16_tts=False,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(VoiceProviderCapabilityUnavailable):
            await module.transcribe(b"audio", audio_format="wav")
        with pytest.raises(VoiceProviderCapabilityUnavailable):
            _ = [chunk async for chunk in module.synthesize("测试", voice="冰糖")]
        assert calls == 0
    finally:
        await module.aclose()


@pytest.mark.asyncio
async def test_voice_module_rejects_malformed_sse_and_invalid_pcm16() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sse([{"choices": [{"delta": {"audio": {"data": "AQ=="}}}]}]),
        )

    module = MiMoVoiceModule(
        asr_url="https://voice.test/v1",
        tts_url="https://voice.test/v1",
        api_key="test-key",
        auth_header="api-key",
        asr_model="mimo-v2.5-asr",
        tts_model="mimo-v2.5-tts",
        default_voice="冰糖",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(VoiceProviderInvalidResponse, match="PCM16"):
            _ = [chunk async for chunk in module.synthesize("测试", voice="冰糖")]
    finally:
        await module.aclose()


@pytest.mark.asyncio
async def test_voice_tts_redacts_text_and_style_before_provider_egress() -> None:
    pcm = b"\x01\x00"
    raw_text = "患者姓名：李雷，电话 13800138000，请慢一点朗读。"
    raw_style = "name: John Smith, token=provider-secret 温和朗读"

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        outbound = json.dumps(payload, ensure_ascii=False)
        for value in ("李雷", "13800138000", "John Smith", "provider-secret"):
            assert value not in outbound
        assert payload["messages"][0]["content"] == "您, token=[REDACTED] 温和朗读"
        assert payload["messages"][1]["content"] == "您，电话 [PHONE]，请慢一点朗读。"
        return httpx.Response(
            200,
            text=_sse(
                [{"choices": [{"delta": {"audio": {"data": base64.b64encode(pcm).decode()}}}]}]
            ),
        )

    module = MiMoVoiceModule(
        asr_url="https://voice.test/v1",
        tts_url="https://voice.test/v1",
        api_key="test-key",
        auth_header="authorization",
        asr_model="mimo-v2.5-asr",
        tts_model="mimo-v2.5-tts",
        default_voice="冰糖",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    try:
        chunks = [
            chunk async for chunk in module.synthesize(raw_text, voice="冰糖", style=raw_style)
        ]
        assert chunks == [pcm]
    finally:
        await module.aclose()
