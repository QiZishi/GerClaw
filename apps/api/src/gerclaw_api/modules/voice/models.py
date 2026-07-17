"""Strict ASR/TTS contracts for the FastAPI voice boundary."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

VOICE_NAMES = ("冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean")
VoiceName = Literal["冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"]
AudioFormat = Literal["wav", "mp3"]
VOICE_ASR_RESPONSE_SCHEMA_VERSION: Final[Literal["voice-asr-response-v1"]] = (
    "voice-asr-response-v1"
)
VOICE_TTS_MEDIA_CONTRACT_VERSION: Final[Literal["voice-tts-pcm16-v1"]] = (
    "voice-tts-pcm16-v1"
)


class VoiceASRRequest(BaseModel):
    """A bounded base64 audio payload; decoded bytes are never persisted."""

    model_config = ConfigDict(extra="forbid")

    audio: str = Field(min_length=4, max_length=10 * 1024 * 1024)
    format: AudioFormat


class VoiceASRResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["voice-asr-response-v1"] = VOICE_ASR_RESPONSE_SCHEMA_VERSION
    text: str = Field(min_length=1, max_length=4_000)


class VoiceTTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4_000)
    voice: VoiceName | None = None
    style: str | None = Field(default=None, min_length=1, max_length=300)
