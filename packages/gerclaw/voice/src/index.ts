/** Qianwen realtime speech bridge for GerClaw's chat composer. */
import { randomUUID } from 'node:crypto'
import type { IncomingMessage } from 'node:http'
import type { Duplex } from 'node:stream'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'
import WebSocket, { WebSocketServer } from 'ws'

export interface VoiceConfig {
  asrApiKey?: string
  asrUrl?: string
  ttsApiKey?: string
  ttsUrl?: string
  asrModel?: string
  ttsModel?: string
  ttsVoice?: string
  ttsInstructions?: string
}
export interface VoiceAudioChunk {
  audio: Uint8Array
  sampleRate: 24000
  channels: 1
  encoding: 'pcm16le'
}
type UpstreamEvent = {
  type?: string
  delta?: string
  transcript?: string
  text?: string
  error?: { message?: string }
}

const DEFAULT_ASR_MODEL = 'qwen3-asr-flash-realtime'
const DEFAULT_TTS_MODEL = 'qwen3-tts-instruct-flash-realtime'
const DEFAULT_VOICE = 'Cherry'
const DEFAULT_INSTRUCTIONS = '用温和、清晰、关怀的中文语气朗读，语速适中。'
const MAX_AUDIO_BYTES = 16 * 1024 * 1024
const MAX_TEXT_LENGTH = 8000
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
      reject(new Error('语音服务连接超时'))
    }, 15_000)
    const cleanup = () => {
      clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
    }
    const abort = () => {
      cleanup()
      socket.terminate()
      reject(new DOMException('语音请求已取消', 'AbortError'))
    }
    socket.once('open', () => {
      cleanup()
      resolve()
    })
    socket.once('error', (error) => {
      cleanup()
      reject(error)
    })
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
  const abort = () => {
    socket.terminate()
  }
  signal.addEventListener('abort', abort, { once: true })
  socket.once('close', () => {
    signal.removeEventListener('abort', abort)
  })
  return socket
}

/**
 * Account-local Qianwen realtime ASR/TTS service.
 * Raw audio only crosses the live socket and is never written to session/storage.
 */
export class VoiceService extends Service {
  static inject = ['webServer']
  private readonly server = new WebSocketServer({ noServer: true })
  private readonly live = new Set<AbortController>()
  constructor(
    ctx: Context,
    private readonly config: VoiceConfig = {},
  ) {
    super(ctx, 'gerclawVoice')
  }
  protected [Service.init](): void {
    const disposeUpgrade = this.ctx.webServer.registerUpgrade({
      path: '/gerclaw/api/voice/asr-stream',
      handler: (req, socket, head) => {
        this.handleAsrUpgrade(req, socket, head)
      },
    })
    this.ctx.effect(
      () => async () => {
        disposeUpgrade()
        for (const controller of this.live) controller.abort()
        for (const client of this.server.clients) client.terminate()
        await new Promise<void>((resolve) => {
          this.server.close(() => {
            resolve()
          })
        })
      },
      'gerclaw.voice.realtime',
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
  private handleAsrUpgrade(req: IncomingMessage, socket: Duplex, head: Buffer): void {
    this.server.handleUpgrade(req, socket, head, (browser) => {
      const controller = new AbortController()
      this.live.add(controller)
      browser.once('close', () => {
        controller.abort()
      })
      browser.once('error', () => {
        controller.abort()
      })
      void this.bridgeAsr(browser, controller).finally(() => {
        this.live.delete(controller)
        if (browser.readyState === WebSocket.OPEN) browser.close(1000)
      })
    })
  }
  private async bridgeAsr(
    browser: WebSocket,
    controller: AbortController,
  ): Promise<void> {
    const missing = this.missingForAsr()
    if (missing.length) {
      browser.send(JSON.stringify({
        type: 'error',
        message: `缺少环境变量：${missing.join('、')}`,
      }))
      return
    }
    const model = this.config.asrModel ?? DEFAULT_ASR_MODEL
    const socket = upstream(
      realtimeUrl(this.config.asrUrl ?? '', model),
      this.config.asrApiKey ?? '',
      controller.signal,
    )
    await waitForOpen(socket, controller.signal)
    await waitForEvent(socket, 'session.created', controller.signal)
    const started = performance.now()
    let audioBytes = 0
    let committed = false
    let finalText = ''
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
    await waitForEvent(socket, 'session.updated', controller.signal)
    browser.send(JSON.stringify({ type: 'ready' }))
    await new Promise<void>((resolve, reject) => {
      let settled = false
      const finish = () => {
        if (settled) return
        settled = true
        browser.off('message', onBrowser)
        resolve()
      }
      const fail = (error: unknown) => {
        if (settled) return
        settled = true
        if (browser.readyState === WebSocket.OPEN)
          browser.send(JSON.stringify({ type: 'error', message: safeMessage(error) }))
        browser.off('message', onBrowser)
        socket.terminate()
        reject(error instanceof Error ? error : new Error(safeMessage(error)))
      }
      const onBrowser = (data: WebSocket.RawData, binary: boolean) => {
        if (controller.signal.aborted) return
        if (binary) {
          const chunk = Buffer.from(data as Buffer)
          audioBytes += chunk.length
          if (audioBytes > MAX_AUDIO_BYTES) {
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
      socket.on('message', (data) => {
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
          const text = (event.text ?? event.transcript ?? event.delta ?? '').trim()
          if (text && browser.readyState === WebSocket.OPEN)
            browser.send(JSON.stringify({ type: 'partial', text }))
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
          socket.close(1000)
          finish()
        }
      })
      socket.once('error', fail)
      socket.once('close', () => {
        if (!controller.signal.aborted && !settled)
          fail(new Error('语音识别连接提前关闭'))
      })
    })
  }
  /** Stream 24 kHz PCM16LE chunks for a completed assistant reply. */
  async *synthesizeStream(
    text: string,
    signal?: AbortSignal,
  ): AsyncGenerator<VoiceAudioChunk> {
    const missing = this.missingForTts()
    if (missing.length)
      throw new Error(`缺少环境变量：${missing.join('、')}`)
    const cleaned = text.trim()
    if (!cleaned) throw new Error('语音回复内容不能为空')
    if (cleaned.length > MAX_TEXT_LENGTH) throw new Error('语音回复内容过长')
    const controller = new AbortController()
    const abort = () => {
      controller.abort()
    }
    signal?.addEventListener('abort', abort, { once: true })
    this.live.add(controller)
    const model = this.config.ttsModel ?? DEFAULT_TTS_MODEL
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
      await waitForOpen(socket, controller.signal)
      await waitForEvent(socket, 'session.created', controller.signal)
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
      socket.send(JSON.stringify({
        event_id: randomUUID(),
        type: 'session.update',
        session: {
          voice: this.config.ttsVoice ?? DEFAULT_VOICE,
          mode: 'commit',
          language_type: 'Chinese',
          response_format: 'pcm',
          sample_rate: 24000,
          instructions: this.config.ttsInstructions ?? DEFAULT_INSTRUCTIONS,
          optimize_instructions: false,
        },
      }))
      socket.send(JSON.stringify({
        event_id: randomUUID(),
        type: 'input_text_buffer.append',
        text: cleaned,
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

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawVoice: VoiceService
  }
}
export default VoiceService
