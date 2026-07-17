# Voice

`modules/voice` is the FastAPI Runtime adapter for MiMo-compatible ASR and
streaming TTS. It exposes authenticated `POST /api/v1/voice/asr` and
`POST /api/v1/voice/tts` endpoints. ASR accepts bounded WAV/MP3 base64 and
returns only a final transcript; TTS yields raw 24 kHz mono PCM16LE chunks so
the client retains pause, resume, stop and progress control.

The module is created only when all MiMo URL, key, model and allowlisted voice
environment settings exist. Calls require `voice:use`, the common rate limiter,
bounded provider timeouts, and return stable provider-independent errors. It
does not persist audio, transcript, synthesis text, provider bodies, or keys.

Before every provider call it persists a PHI-free egress decision and then
marks it succeeded or failed. TTS records the versioned text-redaction category
counts. ASR records only the fixed `external_asr_audio` purpose,
`audio-egress-v1`, processor and outcome with an empty findings list; this does
not imply that the unmodified audio was de-identified or consented.

The MVP browser path calls these FastAPI endpoints only through the restricted
`/api/gerclaw/voice/*` BFF allowlist. The BFF preserves the authenticated
principal and opaque trace ID; the browser wraps the trusted PCM16 response in
a WAV container solely for native playback. This keeps the existing message
player's pause, resume, stop and progress controls while eliminating the legacy
direct-provider BFF route. ASR has a dedicated bounded request limit because
base64 WAV payloads are larger than ordinary JSON requests.
