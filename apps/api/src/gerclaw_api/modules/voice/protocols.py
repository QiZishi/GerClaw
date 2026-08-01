"""Provider-independent Voice module contract."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol

from gerclaw_api.modules.voice.models import AudioFormat


class VoiceModule(Protocol):
    """ASR plus PCM16 streaming TTS without durable audio storage."""

    async def transcribe(self, audio_data: bytes, *, audio_format: AudioFormat) -> str:
        """Return one final, bounded transcript."""

    async def synthesize(self, text: str, *, style: str | None = None) -> AsyncGenerator[bytes, None]:
        """Yield 24 kHz mono PCM16LE chunks."""

    async def aclose(self) -> None:
        """Release provider resources."""
