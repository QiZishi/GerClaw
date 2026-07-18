"""FastAPI Runtime voice contracts and MiMo-compatible implementation."""

from gerclaw_api.modules.voice.module import (
    MiMoVoiceModule,
    VoiceProviderCapabilityUnavailable,
    VoiceProviderError,
    VoiceProviderInvalidResponse,
    VoiceProviderUnavailable,
    create_voice_module,
)
from gerclaw_api.modules.voice.protocols import VoiceModule

__all__ = [
    "MiMoVoiceModule",
    "VoiceModule",
    "VoiceProviderCapabilityUnavailable",
    "VoiceProviderError",
    "VoiceProviderInvalidResponse",
    "VoiceProviderUnavailable",
    "create_voice_module",
]
