/** dsh-talk lifecycle/cache/projection adapted to Qianwen-only GerClaw speech. */
import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import { SessionId, type Session } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-host-webserver'
import type {} from '@deepseek-ai/dsh-session-projection'
import type { GerclawVoiceEvent, SpeechAudioChunk } from '@gerclaw/speech'
import { Config, type ResolvedConfig } from './config.ts'
import {
  applyTalkSpeechProjection,
  applyGerclawVoiceProjection,
  GERCLAW_VOICE_PROJECTION_STATE_VERSION,
  initTalkSpeechProjection,
  initGerclawVoiceProjection,
  TALK_SPEECH_PROJECTION_STATE_VERSION,
  talkSpeechProjectionSchema,
  gerclawVoiceProjectionSchema,
  viewTalkSpeechProjection,
  viewGerclawVoiceProjection,
} from './projection.ts'
import { sanitizeText } from './sanitize.ts'
import type { TalkAudio, TalkInterruptResult, TalkStatus } from './wire.ts'

const MAX_UTTERANCE_COUNT = 64
const MAX_TTS_REQUEST_BYTES = 128 * 1024

const readVoiceBody = async (req: AsyncIterable<Uint8Array>): Promise<{ text?: unknown; voice?: unknown }> => {
  const chunks: Buffer[] = []
  let total = 0
  for await (const chunk of req) {
    const part = Buffer.from(chunk)
    total += part.byteLength
    if (total > MAX_TTS_REQUEST_BYTES) throw new Error('朗读内容过长')
    chunks.push(part)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as { text?: unknown; voice?: unknown }
}

interface StoredUtterance {
  mime: 'audio/L16;rate=24000;channels=1'
  data: Uint8Array
  text: string
  engine: 'qianwen'
}

export interface StreamSpeakOptions {
  session?: Session
  signal?: AbortSignal
  voice?: string
}

declare module '@deepseek-ai/cordis' {
  interface Context { talk: TalkService }
}

export function resolveTtsEngine(): 'qianwen' { return 'qianwen' }
export function resolveSttEngine(): 'qianwen' { return 'qianwen' }

export class TalkService extends TypertRemoteService {
  static inject = ['speech', 'sessions', 'sessionProjections', 'webServer']
  static Config = Config
  private readonly utterances = new Map<string, StoredUtterance>()
  private totalCachedBytes = 0
  private readonly activeSyntheses = new Map<string, AbortController>()

  constructor(
    ctx: Context,
    private readonly resolved: ResolvedConfig,
  ) {
    super(ctx, 'talk')
    ctx.effect(() => ctx.webServer.registerUpgrade({
      path: '/gerclaw/api/voice/asr-stream',
      handler: (req, socket, head) => {
        const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`)
        const rawSessionId = url.searchParams.get('sessionId')
        const session = rawSessionId ? ctx.sessions.get(SessionId(rawSessionId)) : undefined
        if (session === undefined) {
          socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n')
          return
        }
        ctx.speech.acceptAsrUpgrade(req, socket, head, (event) => {
          session.append('gerclaw/voice', event)
          void ctx.sessions.flush(session)
        })
      },
    }), 'gerclaw voice: ASR upgrade route')
    ctx.effect(() => ctx.webServer.register({
      kind: 'exact',
      path: '/gerclaw/api/voice/tts',
      handler: async (req, res) => {
        if (req.method !== 'POST') {
          res.writeHead(405, { Allow: 'POST' })
          res.end()
          return
        }
        const controller = new AbortController()
        const abort = () => {
          if (!res.writableEnded) controller.abort('client-disconnected')
        }
        res.once('close', abort)
        try {
          const rawSessionId = req.headers['x-gerclaw-session-id']
          const sessionId = typeof rawSessionId === 'string' ? rawSessionId : undefined
          const session = sessionId === undefined ? undefined : ctx.sessions.get(SessionId(sessionId))
          if (session === undefined) throw new Error('当前对话会话不存在，无法朗读')
          const body = await readVoiceBody(req)
          const text = typeof body.text === 'string' ? body.text : ''
          const voice = typeof body.voice === 'string' ? body.voice : undefined
          const started = performance.now()
          const stream = this.synthesizeForPlayback(text, {
            session,
            signal: controller.signal,
            ...(voice === undefined ? {} : { voice }),
          })
          const first = await stream.next()
          if (first.done) throw new Error('朗读服务没有返回音频')
          res.writeHead(200, {
            'Content-Type': 'application/x-ndjson; charset=utf-8',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
          })
          res.write(`${JSON.stringify({ type: 'meta', sampleRate: 24000, channels: 1, encoding: 'pcm16le' })}\n`)
          res.write(`${JSON.stringify({ type: 'audio', audio: Buffer.from(first.value.audio).toString('base64') })}\n`)
          for await (const chunk of stream)
            res.write(`${JSON.stringify({ type: 'audio', audio: Buffer.from(chunk.audio).toString('base64') })}\n`)
          res.end(`${JSON.stringify({ type: 'done', elapsedMs: Math.round(performance.now() - started) })}\n`)
          await ctx.sessions.flush(session)
        } catch (error) {
          if (res.headersSent) res.destroy()
          else {
            const message = sanitizeText(error instanceof Error ? error.message : '朗读失败', 300)
            const payload = JSON.stringify({ error: message })
            res.writeHead(400, {
              'Content-Type': 'application/json; charset=utf-8',
              'Cache-Control': 'no-store',
            })
            res.end(payload)
          }
        } finally {
          res.off('close', abort)
          controller.abort('request-finished')
        }
      },
    }), 'gerclaw voice: TTS stream route')
    ctx.effect(() => ctx.sessionProjections.register<'talk:speech', ReturnType<typeof initTalkSpeechProjection>>({
      key: 'talk:speech',
      stateSchema: talkSpeechProjectionSchema,
      init: initTalkSpeechProjection,
      apply: applyTalkSpeechProjection,
      wire: {
        viewSchema: talkSpeechProjectionSchema,
        view: viewTalkSpeechProjection,
      },
      stateVersion: TALK_SPEECH_PROJECTION_STATE_VERSION,
    }), 'dsh-talk: talk:speech projection')
    ctx.effect(() => ctx.sessionProjections.register<'gerclaw/voice', ReturnType<typeof initGerclawVoiceProjection>>({
      key: 'gerclaw/voice',
      stateSchema: gerclawVoiceProjectionSchema,
      init: initGerclawVoiceProjection,
      apply: applyGerclawVoiceProjection,
      wire: {
        viewSchema: gerclawVoiceProjectionSchema,
        view: viewGerclawVoiceProjection,
      },
      stateVersion: GERCLAW_VOICE_PROJECTION_STATE_VERSION,
    }), 'gerclaw: voice projection')
    ctx.effect(() => () => {
      for (const controller of this.activeSyntheses.values()) controller.abort('plugin-unloaded')
      this.activeSyntheses.clear()
      this.utterances.clear()
      this.totalCachedBytes = 0
    }, 'gerclaw voice: talk lifecycle')
  }

  /** Stream Qianwen PCM while retaining dsh-talk's interruption and projection event. */
  async *synthesizeForPlayback(
    input: string,
    options: StreamSpeakOptions = {},
  ): AsyncGenerator<SpeechAudioChunk> {
    const spoken = sanitizeText(input, this.resolved.maxSpeakChars)
    if (!spoken) throw new Error('朗读内容不能为空')
    this.interrupt()
    const utteranceId = randomUUID()
    const controller = new AbortController()
    const signal = options.signal === undefined
      ? controller.signal
      : AbortSignal.any([controller.signal, options.signal])
    this.activeSyntheses.set(utteranceId, controller)
    const chunks: Uint8Array[] = []
    let total = 0
    const started = performance.now()
    try {
      for await (const chunk of this.ctx.speech.synthesizeStream(
        spoken,
        signal,
        options.voice ?? this.resolved.ttsVoice,
      )) {
        total += chunk.audio.byteLength
        if (total > 64 * 1024 * 1024)
          throw new Error('朗读音频超过 64 MB 限制')
        chunks.push(chunk.audio)
        yield chunk
      }
      const elapsedMs = Math.round(performance.now() - started)
      const data = Buffer.concat(chunks.map(chunk => Buffer.from(chunk)))
      const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength)
      this.cacheUtterance(utteranceId, bytes, spoken)
      this.appendCompletedEvents(options.session, utteranceId, spoken, total, elapsedMs, options.voice)
    } catch (error) {
      const interrupted = signal.aborted
      const message = interrupted ? '朗读已停止' : sanitizeText(error instanceof Error ? error.message : String(error), 300)
      const interruptionReason = controller.signal.aborted
        ? controller.signal.reason === 'plugin-unloaded' ? 'plugin-unloaded' : 'new-input'
        : options.signal?.aborted ? 'client-disconnected' : undefined
      this.appendFailureEvents(
        options.session,
        utteranceId,
        spoken,
        Math.round(performance.now() - started),
        interrupted,
        message,
        interruptionReason,
      )
      throw error
    } finally {
      this.activeSyntheses.delete(utteranceId)
      controller.abort()
    }
  }

  private appendCompletedEvents(
    session: Session | undefined,
    utteranceId: string,
    text: string,
    audioBytes: number,
    elapsedMs: number,
    voice?: string,
  ): void {
    if (session === undefined) return
    session.append('dsh-talk/speech', {
      kind: 'tts', utteranceId, engine: 'qianwen', text, audioBytes, reason: 'user-read-aloud',
    })
    session.append('gerclaw/voice', {
      version: 1,
      kind: 'tts',
      status: 'completed',
      model: this.ctx.speech.info.ttsModel,
      text,
      elapsedMs,
      ...(voice === undefined ? {} : { voice }),
    })
  }

  private appendFailureEvents(
    session: Session | undefined,
    utteranceId: string,
    text: string,
    elapsedMs: number,
    interrupted: boolean,
    error: string,
    interruptionReason?: GerclawVoiceEvent['interruptionReason'],
  ): void {
    if (session === undefined) return
    session.append('dsh-talk/speech', {
      kind: 'tts', utteranceId, engine: 'qianwen', text, audioBytes: 0,
      reason: 'user-read-aloud', error, ...(interrupted ? { interrupted: true } : {}),
    })
    const event: GerclawVoiceEvent = {
      version: 1,
      kind: 'tts',
      status: interrupted ? 'interrupted' : 'failed',
      model: this.ctx.speech.info.ttsModel,
      text,
      elapsedMs,
      ...(interrupted ? { interruptionReason: interruptionReason ?? 'client-disconnected' } : { error }),
    }
    session.append('gerclaw/voice', event)
  }

  private cacheUtterance(utteranceId: string, data: Uint8Array, text: string): void {
    this.utterances.set(utteranceId, {
      mime: 'audio/L16;rate=24000;channels=1', data, text, engine: 'qianwen',
    })
    this.totalCachedBytes += data.byteLength
    while (
      (this.totalCachedBytes > this.resolved.maxAudioCacheBytes || this.utterances.size > MAX_UTTERANCE_COUNT)
      && this.utterances.size > 1
    ) {
      const oldest = this.utterances.entries().next().value
      if (oldest === undefined || oldest[0] === utteranceId) break
      this.utterances.delete(oldest[0])
      this.totalCachedBytes -= oldest[1].data.byteLength
    }
  }

  @Remote('status')
  status(): TalkStatus {
    return {
      stt: { engine: 'qianwen', model: this.ctx.speech.info.asrModel, language: this.resolved.sttLanguage },
      tts: { engine: 'qianwen', model: this.ctx.speech.info.ttsModel, voice: this.resolved.ttsVoice },
      record: {
        enabled: this.resolved.recordEnabled,
        hotkey: this.resolved.recordHotkey,
        maxSeconds: 60,
      },
      interrupt: this.resolved.interruptEnabled,
    }
  }

  @Remote('audio')
  audio(utteranceId: string): TalkAudio | null {
    const stored = this.utterances.get(utteranceId)
    if (stored === undefined) return null
    return { utteranceId, ...stored, data: Buffer.from(stored.data).toString('base64') }
  }

  @Remote('interrupt')
  interrupt(): TalkInterruptResult {
    let stopped = false
    for (const controller of this.activeSyntheses.values()) {
      stopped = true
      controller.abort('new-input')
    }
    this.activeSyntheses.clear()
    return { stopped }
  }
}

export default TalkService
