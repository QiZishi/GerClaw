/** dsh-talk lifecycle/cache/projection adapted to Qianwen-only GerClaw speech. */
import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type { Session } from '@deepseek-ai/dsh-session'
import type { ResolvedConfig } from './config.ts'
import { sanitizeText } from './sanitize.ts'
import type { GerclawVoiceEvent } from './vocabulary.ts'
import type { TalkAudio, TalkInterruptResult, TalkStatus } from './wire.ts'
import type { VoiceAudioChunk } from './qianwen.ts'

const MAX_UTTERANCE_COUNT = 64

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
  static inject = ['gerclawVoice']
  private readonly utterances = new Map<string, StoredUtterance>()
  private totalCachedBytes = 0
  private readonly activeSyntheses = new Map<string, AbortController>()

  constructor(
    ctx: Context,
    private readonly resolved: ResolvedConfig,
  ) {
    super(ctx, 'talk')
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
  ): AsyncGenerator<VoiceAudioChunk> {
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
      for await (const chunk of this.ctx.gerclawVoice.synthesizeStream(
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
      model: this.resolved.ttsModel,
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
      model: this.resolved.ttsModel,
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
      stt: { engine: 'qianwen', model: this.resolved.asrModel, language: this.resolved.sttLanguage },
      tts: { engine: 'qianwen', model: this.resolved.ttsModel, voice: this.resolved.ttsVoice },
      record: {
        enabled: this.resolved.recordEnabled,
        hotkey: this.resolved.recordHotkey,
        maxSeconds: 60,
        autoSubmit: true,
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
