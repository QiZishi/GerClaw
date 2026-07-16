# Voice Module Instructions

## Responsibility

This module owns FastAPI-runtime ASR and streaming PCM16 TTS provider adaptation.
It is not a clinical decision engine and never persists raw audio, transcript,
speech text, provider bodies, or credentials.

## Invariants

- Only WAV/MP3 ASR input within the route size limit is accepted.
- TTS is PCM16LE, 24 kHz, mono and streamed; the module must not silently
  downgrade to a pre-generated clinical statement.
- Provider failures are stable, PHI-free errors. Do not log request or response
  bodies.
- Every external call has a bounded timeout and is behind `voice:use` scope and
  the shared tenant/actor rate limiter.

## Change and test rules

- Test successful ASR/TTS SSE parsing, malformed provider data, size/format
  rejection, missing scope and unavailable configuration.
- Do not invoke a live voice provider in ordinary tests.
