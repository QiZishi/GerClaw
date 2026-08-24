/** Qianwen realtime speech bridge for GerClaw's chat composer. */
import { randomUUID } from 'node:crypto'
import type { IncomingMessage } from 'node:http'
import type { Duplex } from 'node:stream'
import { Context, Service } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import {
  QIANWEN_ASR_MODEL,
  QIANWEN_TTS_MODEL,
  SpeechProvider,
  type SpeechAudioChunk,
  type SpeechEventSink,
  type SpeechProviderInfo,
} from '@gerclaw/speech'
import WebSocket, { WebSocketServer } from 'ws'

export interface QianwenSpeechConfig {
  asrApiKey?: string
  asrUrl?: string
  ttsApiKey?: string
  ttsUrl?: string
  asrModel?: string
  ttsModel?: string
  ttsVoice?: string
  ttsInstructions?: string
}
type UpstreamEvent = {
  type?: string
  delta?: string
  transcript?: string
  text?: string
  stash?: string
  error?: { message?: string }
}

const DEFAULT_VOICE = 'Cherry'
const DEFAULT_INSTRUCTIONS = '用温和、清晰、关怀的中文语气朗读，语速适中。'
/** Exactly 60 seconds of 16 kHz mono PCM16LE. */
export const MAX_ASR_AUDIO_BYTES = 16_000 * 2 * 60
export const MAX_TTS_SEGMENT_CHARS = 1_200
const safeMessage = (error: unknown) =>
  error instanceof Error ? error.message : '语音服务连接失败'
const realtimeUrl = (base: string, model: string) => {
  const url = new URL(base)
  url.searchParams.set('model', model)
  return url.toString()
}
const waitForOpen = (socket: WebSocket, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup()
      reject(new Error('语音服务连接超时'))
    }, 15_000)
    const cleanup = () => {
      clearTimeout(timer)
      socket.off('open', onOpen)
      socket.off('error', onError)
      signal?.removeEventListener('abort', abort)
    }
    const abort = () => {
      cleanup()
      reject(new DOMException('语音请求已取消', 'AbortError'))
    }
    const onOpen = () => {
      cleanup()
      resolve()
    }
    const onError = (error: Error) => {
      cleanup()
      reject(error)
    }
    socket.once('open', onOpen)
    socket.once('error', onError)
    signal?.addEventListener('abort', abort, { once: true })
  })
const rawText = (data: WebSocket.RawData): string => {
  if (Array.isArray(data)) return Buffer.concat(data).toString()
  if (Buffer.isBuffer(data)) return data.toString()
  return Buffer.from(new Uint8Array(data)).toString()
}
const parseEvent = (data: WebSocket.RawData): UpstreamEvent => {
  try {
    return JSON.parse(rawText(data)) as UpstreamEvent
  } catch {
    throw new Error('语音服务返回了无法识别的数据')
  }
}
const waitForEvent = (
  socket: WebSocket,
  type: string,
  signal: AbortSignal,
) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(
      () => {
        cleanup()
        reject(new Error('语音服务初始化超时'))
      },
      15_000,
    )
    const cleanup = () => {
      clearTimeout(timer)
      socket.off('message', onMessage)
      socket.off('error', onError)
      signal.removeEventListener('abort', onAbort)
    }
    const onMessage = (data: WebSocket.RawData) => {
      let event: UpstreamEvent
      try {
        event = parseEvent(data)
      } catch (error) {
        cleanup()
        reject(error instanceof Error ? error : new Error(safeMessage(error)))
        return
      }
      if (event.type === 'error') {
        cleanup()
        reject(new Error(event.error?.message ?? '语音服务初始化失败'))
      } else if (event.type === type) {
        cleanup()
        resolve()
      }
    }
    const onError = (error: Error) => {
      cleanup()
      reject(error)
    }
    const onAbort = () => {
      cleanup()
      reject(new DOMException('语音请求已取消', 'AbortError'))
    }
    socket.on('message', onMessage)
    socket.once('error', onError)
    signal.addEventListener('abort', onAbort, { once: true })
  })
const upstream = (url: string, apiKey: string, signal: AbortSignal): WebSocket => {
  const socket = new WebSocket(url, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'OpenAI-Beta': 'realtime=v1',
    },
  })
  // ws emits an error when a still-connecting socket is terminated. During
  // cancellation that error is expected, but it must remain observed after
  // the handshake waiter has detached its listener.
  const observeAbortError = () => {}
  const abort = () => {
    socket.on('error', observeAbortError)
    socket.terminate()
  }
  signal.addEventListener('abort', abort, { once: true })
  socket.once('close', () => {
    signal.removeEventListener('abort', abort)
    socket.off('error', observeAbortError)
  })
  return socket
}

/** Sentence-aware Qianwen requests; playback remains continuous in the browser queue. */
export function splitTtsText(input: string, limit = MAX_TTS_SEGMENT_CHARS): string[] {
  const text = input.trim()
  if (!text) return []
  const sentences = text.match(/[^。！？!?；;\n]+[。！？!?；;\n]?/gu) ?? [text]
  const segments: string[] = []
  let current = ''
  for (const sentence of sentences.map(value => value.trim()).filter(Boolean)) {
    if (sentence.length > limit) {
      if (current) { segments.push(current); current = '' }
      for (let offset = 0; offset < sentence.length; offset += limit)
        segments.push(sentence.slice(offset, offset + limit))
      continue
    }
    if (current && current.length + sentence.length > limit) {
      segments.push(current)
      current = sentence
    } else current += sentence
  }
  if (current) segments.push(current)
  return segments
}

/**
 * Account-local Qianwen realtime ASR/TTS service.
 * Raw audio only crosses the live socket and is never written to session/storage.
 */
export class QianwenSpeechProvider extends SpeechProvider {
  static Config: z<QianwenSpeechConfig> = z.object({
    asrApiKey: z.string().required(),
    asrUrl: z.string().required(),
    ttsApiKey: z.string().required(),
    ttsUrl: z.string().required(),
    asrModel: z.const(QIANWEN_ASR_MODEL).required(),
    ttsModel: z.const(QIANWEN_TTS_MODEL).required(),
    ttsVoice: z.string().default(DEFAULT_VOICE),
    ttsInstructions: z.string().default(DEFAULT_INSTRUCTIONS),
  }) as unknown as z<QianwenSpeechConfig>

  readonly info: SpeechProviderInfo
  private readonly server = new WebSocketServer({ noServer: true })
  private readonly live = new Set<AbortController>()

  constructor(
    ctx: Context,
    private readonly config: QianwenSpeechConfig,
  ) {
    super(ctx)
    this.info = Object.freeze({
      engine: 'qianwen',
      asrModel: QIANWEN_ASR_MODEL,
      ttsModel: QIANWEN_TTS_MODEL,
      defaultVoice: config.ttsVoice ?? DEFAULT_VOICE,
    })
  }

  protected [Service.init](): void {
    this.ctx.effect(
      () => async () => {
        for (const controller of this.live) controller.abort('plugin-unloaded')
        for (const client of this.server.clients) client.terminate()
        await new Promise<void>((resolve) => {
          this.server.close(() => {
            resolve()
          })
        })
      },
      'gerclaw.speech-qianwen.realtime',
    )
  }
  missingForAsr(): string[] {
    const values: Record<string, string | undefined> = {
      MODEL_ASR_KEY: this.config.asrApiKey,
      MODEL_ASR_URL: this.config.asrUrl,
      ASR_MODEL: this.config.asrModel,
    }
    return Object.keys(values).filter(name => !values[name])
  }
  missingForTts(): string[] {
    const values: Record<string, string | undefined> = {
      MODEL_TTS_KEY: this.config.ttsApiKey,
      MODEL_TTS_URL: this.config.ttsUrl,
      TTS_MODEL: this.config.ttsModel,
    }
    return Object.keys(values).filter(name => !values[name])
  }
  acceptAsrUpgrade(
    req: IncomingMessage,
    socket: Duplex,
    head: Buffer,
    emit: SpeechEventSink,
  ): void {
    this.server.handleUpgrade(req, socket, head, (browser) => {
      const controller = new AbortController()
      let emitted = false
      this.live.add(controller)
      browser.once('close', () => {
        controller.abort('client-disconnected')
      })
      browser.once('error', () => {
        controller.abort('client-disconnected')
      })
      void this.bridgeAsr(browser, controller, (event) => {
        emitted = true
        emit(event)
      })
        .catch((error: unknown) => {
          // bridgeAsr sends errors that occur after the upstream session has
          // started. This covers failed handshakes as well, while preserving
          // one durable outcome event for the request.
          if (!emitted) {
            const message = safeMessage(error)
            emit({
              version: 1,
              kind: 'asr',
              status: 'failed',
              model: this.config.asrModel ?? QIANWEN_ASR_MODEL,
              text: '',
              elapsedMs: 0,
              error: message,
            })
            if (browser.readyState === WebSocket.OPEN)
              browser.send(JSON.stringify({ type: 'error', message }))
          }
        })
        .finally(() => {
          controller.abort('client-disconnected')
          this.live.delete(controller)
          if (browser.readyState === WebSocket.OPEN) browser.close(1000)
        })
    })
  }
  private async bridgeAsr(
    browser: WebSocket,
    controller: AbortController,
    emit: SpeechEventSink,
  ): Promise<void> {
    const started = performance.now()
    const model = this.config.asrModel ?? QIANWEN_ASR_MODEL
    const missing = this.missingForAsr()
    if (missing.length) {
      const message = `缺少环境变量：${missing.join('、')}`
      emit({
        version: 1,
        kind: 'asr',
        status: 'failed',
        model,
        text: '',
        elapsedMs: Math.round(performance.now() - started),
        error: message,
      })
      if (browser.readyState === WebSocket.OPEN)
        browser.send(JSON.stringify({ type: 'error', message }))
      return
    }
    const socket = upstream(
      realtimeUrl(this.config.asrUrl ?? '', model),
      this.config.asrApiKey ?? '',
      controller.signal,
    )
    await Promise.all([
      waitForOpen(socket, controller.signal),
      waitForEvent(socket, 'session.created', controller.signal),
    ])
    let audioBytes = 0
    let committed = false
    let finalText = ''
    let eventPersisted = false
    const appendVoiceEvent = (event: Parameters<SpeechEventSink>[0]): void => {
      if (eventPersisted) return
      eventPersisted = true
      emit(event)
    }
    const updated = waitForEvent(socket, 'session.updated', controller.signal)
    socket.send(JSON.stringify({
      event_id: randomUUID(),
      type: 'session.update',
      session: {
        modalities: ['text'],
        input_audio_format: 'pcm',
        sample_rate: 16000,
        input_audio_transcription: { language: 'zh' },
        turn_detection: null,
      },
    }))
    await updated
    browser.send(JSON.stringify({ type: 'ready' }))
    await new Promise<void>((resolve, reject) => {
      let settled = false
      const onUpstream = (data: WebSocket.RawData) => {
        let event: UpstreamEvent
        try {
          event = parseEvent(data)
        } catch (error) {
          fail(error)
          return
        }
        if (event.type === 'error') {
          fail(new Error(event.error?.message ?? '语音识别失败'))
          return
        }
        if (event.type === 'conversation.item.input_audio_transcription.text') {
          const text = `${event.text ?? ''}${event.stash ?? ''}`.trim()
          if (text && browser.readyState === WebSocket.OPEN)
            browser.send(JSON.stringify({ type: 'partial', text }))
        }
        if (event.type === 'conversation.item.input_audio_transcription.failed') {
          fail(new Error(event.error?.message ?? '语音识别失败'))
          return
        }
        if (event.type === 'conversation.item.input_audio_transcription.completed') {
          finalText = (event.transcript ?? event.text ?? finalText).trim()
          if (browser.readyState === WebSocket.OPEN)
            browser.send(JSON.stringify({
              type: 'final',
              text: finalText,
              model,
              elapsedMs: Math.round(performance.now() - started),
            }))
        }
        if (event.type === 'session.finished') {
          if (!finalText) {
            fail(new Error('没有识别出可用语音'))
            return
          }
          if (browser.readyState === WebSocket.OPEN)
            browser.send(JSON.stringify({ type: 'done' }))
          appendVoiceEvent({
            version: 1,
            kind: 'asr',
            status: 'completed',
            model,
            text: finalText,
            elapsedMs: Math.round(performance.now() - started),
          })
          socket.close(1000)
          finish()
        }
      }
      const finish = () => {
        if (settled) return
        settled = true
        browser.off('message', onBrowser)
        socket.off('message', onUpstream)
        socket.off('error', fail)
        socket.off('close', onClose)
        controller.signal.removeEventListener('abort', onAbort)
        resolve()
      }
      const fail = (error: unknown) => {
        if (settled) return
        settled = true
        const message = safeMessage(error)
        appendVoiceEvent({
          version: 1,
          kind: 'asr',
          status: 'failed',
          model,
          text: finalText,
          elapsedMs: Math.round(performance.now() - started),
          error: message,
        })
        if (browser.readyState === WebSocket.OPEN)
          browser.send(JSON.stringify({ type: 'error', message }))
        browser.off('message', onBrowser)
        socket.off('message', onUpstream)
        socket.off('error', fail)
        socket.off('close', onClose)
        controller.signal.removeEventListener('abort', onAbort)
        socket.terminate()
        reject(error instanceof Error ? error : new Error(safeMessage(error)))
      }
      const onAbort = () => {
        const reason = controller.signal.reason === 'plugin-unloaded'
          ? 'plugin-unloaded'
          : 'client-disconnected'
        appendVoiceEvent({
          version: 1,
          kind: 'asr',
          status: 'interrupted',
          model,
          text: finalText,
          elapsedMs: Math.round(performance.now() - started),
          interruptionReason: reason,
        })
        finish()
      }
      const onBrowser = (data: WebSocket.RawData, binary: boolean) => {
        if (controller.signal.aborted) return
        if (binary) {
          const chunk = Buffer.from(data as Buffer)
          audioBytes += chunk.length
          if (audioBytes > MAX_ASR_AUDIO_BYTES) {
            fail(new Error('录音过长，请控制在 60 秒以内'))
            return
          }
          socket.send(JSON.stringify({
            event_id: randomUUID(),
            type: 'input_audio_buffer.append',
            audio: chunk.toString('base64'),
          }))
          return
        }
        let command: { type?: string }
        try {
          command = JSON.parse(rawText(data)) as { type?: string }
        } catch {
          fail(new Error('录音控制消息无效'))
          return
        }
        if (command.type === 'cancel') {
          appendVoiceEvent({
            version: 1,
            kind: 'asr',
            status: 'interrupted',
            model,
            text: finalText,
            elapsedMs: Math.round(performance.now() - started),
            interruptionReason: 'user-cancelled',
          })
          controller.abort()
          finish()
        } else if (command.type === 'commit' && !committed) {
          if (audioBytes === 0) {
            fail(new Error('没有收到可识别的录音'))
            return
          }
          committed = true
          socket.send(JSON.stringify({
            event_id: randomUUID(),
            type: 'input_audio_buffer.commit',
          }))
          socket.send(JSON.stringify({
            event_id: randomUUID(),
            type: 'session.finish',
          }))
        }
      }
      browser.on('message', onBrowser)
      controller.signal.addEventListener('abort', onAbort, { once: true })
      const onClose = () => {
        if (!controller.signal.aborted && !settled)
          fail(new Error('语音识别连接提前关闭'))
      }
      socket.on('message', onUpstream)
      socket.once('error', fail)
      socket.once('close', onClose)
    })
  }
  /** Stream 24 kHz PCM16LE chunks for a completed assistant reply. */
  async *synthesizeStream(
    text: string,
    signal?: AbortSignal,
    requestedVoice?: string,
  ): AsyncGenerator<SpeechAudioChunk> {
    const missing = this.missingForTts()
    if (missing.length)
      throw new Error(`缺少环境变量：${missing.join('、')}`)
    const segments = splitTtsText(text)
    if (segments.length === 0) throw new Error('语音回复内容不能为空')
    for (const segment of segments) {
      signal?.throwIfAborted()
      yield* this.synthesizeSegment(segment, signal, requestedVoice)
    }
  }

  private async *synthesizeSegment(
    text: string,
    signal?: AbortSignal,
    requestedVoice?: string,
  ): AsyncGenerator<SpeechAudioChunk> {
    const controller = new AbortController()
    const abort = () => {
      controller.abort()
    }
    signal?.addEventListener('abort', abort, { once: true })
    this.live.add(controller)
    const model = this.config.ttsModel ?? QIANWEN_TTS_MODEL
    const voice = ['Cherry', 'Serena', 'Ethan'].includes(requestedVoice ?? '')
      ? requestedVoice
      : this.config.ttsVoice ?? DEFAULT_VOICE
    const socket = upstream(
      realtimeUrl(this.config.ttsUrl ?? '', model),
      this.config.ttsApiKey ?? '',
      controller.signal,
    )
    const queue: Array<Uint8Array | Error | null> = []
    let wake: (() => void) | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    const push = (value: Uint8Array | Error | null) => {
      queue.push(value)
      wake?.()
      wake = undefined
    }
    try {
      await Promise.all([
        waitForOpen(socket, controller.signal),
        waitForEvent(socket, 'session.created', controller.signal),
      ])
      timeout = setTimeout(
        () => {
          push(new Error('语音合成超时'))
        },
        90_000,
      )
      socket.on('message', (data) => {
        try {
          const event = parseEvent(data)
          if (event.type === 'response.audio.delta' && event.delta)
            push(Buffer.from(event.delta, 'base64'))
          else if (event.type === 'error')
            push(new Error(event.error?.message ?? '语音合成失败'))
          else if (event.type === 'session.finished') {
            clearTimeout(timeout)
            push(null)
          }
        } catch (error) {
          clearTimeout(timeout)
          push(error instanceof Error ? error : new Error('语音合成失败'))
        }
      })
      socket.once('error', (error) => {
        clearTimeout(timeout)
        push(error)
      })
      const updated = waitForEvent(socket, 'session.updated', controller.signal)
      socket.send(JSON.stringify({
        event_id: randomUUID(),
        type: 'session.update',
        session: {
          voice,
          mode: 'commit',
          language_type: 'Chinese',
          response_format: 'pcm',
          sample_rate: 24000,
          instructions: this.config.ttsInstructions ?? DEFAULT_INSTRUCTIONS,
          optimize_instructions: false,
        },
      }))
      await updated
      socket.send(JSON.stringify({
        event_id: randomUUID(),
        type: 'input_text_buffer.append',
        text,
      }))
      socket.send(JSON.stringify({
        event_id: randomUUID(),
        type: 'input_text_buffer.commit',
      }))
      socket.send(JSON.stringify({
        event_id: randomUUID(),
        type: 'session.finish',
      }))
      while (!controller.signal.aborted) {
        if (queue.length === 0)
          await new Promise<void>((resolve) => {
            wake = resolve
          })
        const item = queue.shift()
        if (item === null) break
        if (item instanceof Error) throw item
        if (item && item.length > 0)
          yield {
            audio: item,
            sampleRate: 24000,
            channels: 1,
            encoding: 'pcm16le',
          }
      }
      controller.signal.throwIfAborted()
    } finally {
      signal?.removeEventListener('abort', abort)
      if (timeout) clearTimeout(timeout)
      controller.abort()
      this.live.delete(controller)
      socket.terminate()
    }
  }
}
export default QianwenSpeechProvider
