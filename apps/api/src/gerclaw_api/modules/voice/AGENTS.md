# Voice Module Instructions

## Responsibility

This module owns FastAPI-runtime ASR and streaming PCM16 TTS provider adaptation.
It is not a clinical decision engine and never persists raw audio, transcript,
speech text, provider bodies, or credentials. The FastAPI route may persist
separate PHI-free ASR/TTS egress decisions containing only purpose, processor,
policy version, field name/category counts (if text was classified) and outcome.

## Invariants

- Only WAV/MP3 ASR input within the route size limit is accepted.
- TTS is PCM16LE, 24 kHz, mono and streamed; the module must not silently
  downgrade to a pre-generated clinical statement.
- Provider failures are stable, PHI-free errors. Do not log request or response
  bodies.
- TTS body and style must pass through the versioned `privacy_redaction`
  `external_tts` policy before egress. ASR audio cannot be made safe by text
  redaction; do not claim it is covered without a dedicated consent/minimisation
  design.
- The route must commit a `prepared` egress record before calling the provider,
  then mark it `succeeded` only after a final ASR response or the first valid
  PCM16 packet. ASR uses the explicit `audio-egress-v1` decision with empty
  findings: this records unmodified audio processing, not consent or PHI
  absence. Audit storage failure must stop the provider call; never add text,
  matches, URLs, credentials or audio bytes to that record.
- Every external call has a bounded timeout and is behind `voice:use` scope and
  the shared tenant/actor rate limiter.

## Change and test rules

- Test successful ASR/TTS SSE parsing, malformed provider data, size/format
  rejection, missing scope and unavailable configuration.
- Do not invoke a live voice provider in ordinary tests.
