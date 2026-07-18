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

`voice-capabilities-v1` is a server-owned adapter contract. Production must
explicitly declare streaming ASR and PCM16 TTS support; a request needing an
unsupported capability fails before any provider egress.

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

The public voice transport is versioned: a successful ASR JSON response is
`voice-asr-response-v1` and repeats that literal in
`X-GerClaw-Voice-Contract`; a successful PCM16 TTS stream declares
`voice-tts-pcm16-v1` in the same header. The restricted BFF forwards only the
declared header and the browser requires an exact version before it parses an
ASR response or constructs a playable WAV. This turns a cross-tier format drift
into a controlled client error rather than misleading playback or transcript.

## 维护与演进

**可安全改进。** 可更换 MiMo-compatible provider、改善取消/音质、增加方言评测和 adapter 协商；每种能力以新 capability/transport version 声明，浏览器播放器继续只消费验证过的 PCM16。不可通过浏览器直连 provider 来简化实现。

**不可破坏的契约。** ASR/TTS 必须受 `voice:use`、限流、大小上限、provider timeout、egress outcome 和精确 contract header 保护；不得持久化音频、转写、合成正文、provider body 或 key。浏览器的暂停/继续/停止应控制本地播放，不能伪称能暂停已提交的 provider 合成。

**性能与回归验收。** 覆盖 capability 缺失、权限/大小/格式拒绝、provider timeout、header drift、PCM→WAV 播放控制与 BFF principal 保留；真实 TTS→ASR 烟测记录首字节/完整耗时和稳定错误。10 并发短音频请求应无跨主体 trace 或音频串流，限流拒绝可预期。
