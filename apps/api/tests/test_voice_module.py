"""Offline SSE contract tests for the FastAPI Runtime voice adapter."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from gerclaw_api.modules.voice.module import (
    MiMoVoiceModule,
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
                        {"choices": [{"delta": {"content": "，请说。"}}]},  # noqa: RUF001
                    ]
                ),
            )
        assert payload["audio"] == {"format": "pcm16", "voice": "冰糖"}
        return httpx.Response(
            200,
            text=_sse(
                [
                    {
                        "choices": [
                            {"delta": {"audio": {"data": base64.b64encode(pcm).decode()}}}
                        ]
                    }
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
        assert await module.transcribe(b"audio", audio_format="wav") == "您好，请说。"  # noqa: RUF001
        assert [chunk async for chunk in module.synthesize("测试", voice="冰糖")] == [pcm]
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
