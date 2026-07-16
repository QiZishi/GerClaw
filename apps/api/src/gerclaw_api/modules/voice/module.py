"""MiMo-compatible ASR and PCM16 SSE TTS adapter."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncGenerator
from typing import cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gerclaw_api.config import Settings
from gerclaw_api.modules.voice.models import VOICE_NAMES, AudioFormat, VoiceName

_DEFAULT_STYLE = "用温柔体贴的语调，语速适中，像在关心一位老人的健康状况"  # noqa: RUF001


class VoiceProviderError(RuntimeError):
    """Safe provider error that never carries body, audio, text, or credentials."""


class VoiceProviderUnavailable(VoiceProviderError):
    """Provider networking, timeout, or status failure."""


class VoiceProviderInvalidResponse(VoiceProviderError):
    """Provider returned invalid SSE or invalid encoded content."""


class _DeltaAudio(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: str = Field(min_length=1, max_length=4 * 1024 * 1024)


class _Delta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = Field(default=None, max_length=4_000)
    audio: _DeltaAudio | None = None


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    delta: _Delta


class _StreamEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    choices: list[_Choice] = Field(min_length=1, max_length=10)


class MiMoVoiceModule:
    """One configured provider client; caller controls all user-visible playback."""

    def __init__(
        self,
        *,
        asr_url: str,
        tts_url: str,
        api_key: str,
        auth_header: str,
        asr_model: str,
        tts_model: str,
        default_voice: VoiceName,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Content-Type": "application/json"}
        if auth_header == "api-key":
            headers["api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            transport=transport,
        )
        self._asr_url = f"{asr_url.rstrip('/')}/chat/completions"
        self._tts_url = f"{tts_url.rstrip('/')}/chat/completions"
        self._asr_model = asr_model
        self._tts_model = tts_model
        self.default_voice = default_voice

    @staticmethod
    def _event(line: str) -> _StreamEvent | None:
        if not line.startswith("data:"):
            return None
        payload = line.removeprefix("data:").strip()
        if payload == "[DONE]":
            return None
        try:
            return _StreamEvent.model_validate(json.loads(payload))
        except (json.JSONDecodeError, ValidationError) as error:
            raise VoiceProviderInvalidResponse("voice provider returned invalid SSE") from error

    async def transcribe(self, audio_data: bytes, *, audio_format: AudioFormat) -> str:
        encoded = base64.b64encode(audio_data).decode("ascii")
        payload = {
            "model": self._asr_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": encoded, "format": audio_format},
                        }
                    ],
                }
            ],
            "stream": True,
        }
        fragments: list[str] = []
        try:
            async with self._client.stream("POST", self._asr_url, json=payload) as response:
                if response.status_code >= 400:
                    raise VoiceProviderUnavailable("voice ASR provider rejected the request")
                async for line in response.aiter_lines():
                    event = self._event(line)
                    if event is None:
                        continue
                    for choice in event.choices:
                        if choice.delta.content:
                            fragments.append(choice.delta.content)
        except httpx.TimeoutException as error:
            raise VoiceProviderUnavailable("voice ASR provider timed out") from error
        except httpx.RequestError as error:
            raise VoiceProviderUnavailable("voice ASR provider is unavailable") from error
        transcript = "".join(fragments).strip()
        if not transcript or len(transcript) > 4_000:
            raise VoiceProviderInvalidResponse("voice ASR provider returned no usable transcript")
        return transcript

    async def synthesize(
        self, text: str, *, voice: VoiceName, style: str | None = None
    ) -> AsyncGenerator[bytes, None]:
        payload = {
            "model": self._tts_model,
            "messages": [
                {"role": "user", "content": style or _DEFAULT_STYLE},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": "pcm16", "voice": voice},
            "stream": True,
        }
        yielded = False
        try:
            async with self._client.stream("POST", self._tts_url, json=payload) as response:
                if response.status_code >= 400:
                    raise VoiceProviderUnavailable("voice TTS provider rejected the request")
                async for line in response.aiter_lines():
                    event = self._event(line)
                    if event is None:
                        continue
                    for choice in event.choices:
                        audio = choice.delta.audio
                        if audio is None:
                            continue
                        try:
                            chunk = base64.b64decode(audio.data, validate=True)
                        except ValueError as error:
                            raise VoiceProviderInvalidResponse(
                                "voice TTS provider returned invalid audio"
                            ) from error
                        if not chunk or len(chunk) % 2:
                            raise VoiceProviderInvalidResponse(
                                "voice TTS provider returned invalid PCM16 audio"
                            )
                        yielded = True
                        yield chunk
        except httpx.TimeoutException as error:
            raise VoiceProviderUnavailable("voice TTS provider timed out") from error
        except httpx.RequestError as error:
            raise VoiceProviderUnavailable("voice TTS provider is unavailable") from error
        if not yielded:
            raise VoiceProviderInvalidResponse("voice TTS provider returned no audio")

    async def aclose(self) -> None:
        await self._client.aclose()


def create_voice_module(settings: Settings) -> MiMoVoiceModule | None:
    """Create the adapter only when all required provider settings are present."""

    required = (
        settings.mimo_asr_url,
        settings.mimo_tts_url,
        settings.mimo_api_key,
        settings.asr_model,
        settings.tts_model,
        settings.tts_voice,
    )
    if any(value is None for value in required):
        return None
    tts_voice = settings.tts_voice
    if tts_voice not in VOICE_NAMES:
        raise ValueError("configured TTS voice is not allowlisted")
    api_key = settings.mimo_api_key
    asr_model = settings.asr_model
    tts_model = settings.tts_model
    asr_url = settings.mimo_asr_url
    tts_url = settings.mimo_tts_url
    assert api_key is not None
    assert asr_model is not None
    assert tts_model is not None
    assert asr_url is not None
    assert tts_url is not None
    return MiMoVoiceModule(
        asr_url=str(asr_url),
        tts_url=str(tts_url),
        api_key=api_key.get_secret_value(),
        auth_header=settings.mimo_auth_header,
        asr_model=asr_model,
        tts_model=tts_model,
        default_voice=cast(VoiceName, tts_voice),
        timeout_seconds=settings.external_request_timeout_seconds,
    )
