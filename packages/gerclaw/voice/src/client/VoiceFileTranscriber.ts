import { Service, type Context } from '@deepseek-ai/cordis'

export interface VoiceFileTranscriptionHooks {
  onPartial(text: string): void
  onStatus(message: string): void
}

export interface VoiceFileTranscriptionResult {
  text: string
  elapsedMs: number
}

export interface GerclawVoiceFiles {
  transcribe(
    file: File,
    sessionId: string,
    hooks: VoiceFileTranscriptionHooks,
    signal?: AbortSignal,
  ): Promise<VoiceFileTranscriptionResult>
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawVoiceFiles: GerclawVoiceFiles
  }
}

type VoiceEvent = {
  type?: 'ready' | 'partial' | 'final' | 'done' | 'error'
  text?: string
  message?: string
  elapsedMs?: number
}

const socketUrl = (sessionId: string): string => {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/gerclaw/api/voice/asr-stream?sessionId=${encodeURIComponent(sessionId)}`
}

const isAudioFile = (file: File): boolean =>
  file.type.startsWith('audio/') || /\.(?:aac|flac|m4a|mp3|ogg|opus|wav|webm)$/iu.test(file.name)

const resample = (input: Float32Array, inputRate: number): Float32Array => {
  if (inputRate === 16_000) return input
  const ratio = inputRate / 16_000
  const output = new Float32Array(Math.max(1, Math.round(input.length / ratio)))
  for (let index = 0; index < output.length; index += 1) {
    const position = index * ratio
    const left = Math.floor(position)
    const right = Math.min(input.length - 1, left + 1)
    const fraction = position - left
    output[index] = (input[left] ?? 0) * (1 - fraction) + (input[right] ?? 0) * fraction
  }
  return output
}

const pcm16 = (samples: Float32Array): ArrayBuffer => {
  const values = new Int16Array(samples.length)
  for (let index = 0; index < samples.length; index += 1) {
    values[index] = Math.max(-32_768, Math.min(32_767, Math.round((samples[index] ?? 0) * 32_767)))
  }
  return values.buffer
}

/** Qianwen audio-file adapter consumed by GerClaw's single, general upload control. */
export class VoiceFileTranscriber extends Service implements GerclawVoiceFiles {
  private readonly active = new Set<() => void>()

  constructor(ctx: Context) {
    super(ctx, 'gerclawVoiceFiles')
    ctx.effect(() => () => {
      for (const cancel of [...this.active]) cancel()
      this.active.clear()
    }, 'gerclaw voice: uploaded audio cleanup')
  }

  async transcribe(
    file: File,
    sessionId: string,
    hooks: VoiceFileTranscriptionHooks,
    signal?: AbortSignal,
  ): Promise<VoiceFileTranscriptionResult> {
    if (!isAudioFile(file)) throw new Error('所选文件不是音频文件')
    const isAborted = (): boolean => signal?.aborted ?? false
    if (isAborted()) throw new DOMException('音频识别已取消', 'AbortError')

    const context = new AudioContext()
    const socket = new WebSocket(socketUrl(sessionId))
    socket.binaryType = 'arraybuffer'
    let settled = false
    let cancelled = false
    let finalText = ''
    let elapsedMs = 0
    let timeout = 0

    const cleanup = (cancelUpstream: boolean): void => {
      window.clearTimeout(timeout)
      signal?.removeEventListener('abort', cancel)
      this.active.delete(cancel)
      if (cancelUpstream && socket.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: 'cancel' }))
      socket.close(1000)
      void context.close().catch(() => {})
    }
    const cancel = (): void => {
      if (settled) return
      cancelled = true
      cleanup(true)
    }
    this.active.add(cancel)
    signal?.addEventListener('abort', cancel, { once: true })

    try {
      hooks.onStatus('正在解码音频…')
      const decoded = await context.decodeAudioData(await file.arrayBuffer())
      if (cancelled || isAborted()) throw new DOMException('音频识别已取消', 'AbortError')
      if (decoded.duration > 60.001) throw new Error('音频不能超过 60 秒')

      const mono = new Float32Array(decoded.length)
      for (let channel = 0; channel < decoded.numberOfChannels; channel += 1) {
        const values = decoded.getChannelData(channel)
        for (let index = 0; index < mono.length; index += 1)
          mono[index] = (mono[index] ?? 0) + (values[index] ?? 0) / decoded.numberOfChannels
      }
      const samples = resample(mono, decoded.sampleRate)
      hooks.onStatus('正在连接语音识别…')

      await new Promise<void>((resolve, reject) => {
        if (cancelled || isAborted()) {
          reject(new DOMException('音频识别已取消', 'AbortError'))
          return
        }
        timeout = window.setTimeout(() => reject(new Error('语音识别服务连接超时')), 15_000)
        socket.addEventListener('error', () => reject(new Error('无法连接语音识别服务')), { once: true })
        socket.addEventListener('close', () => {
          if (!settled && finalText === '') reject(new Error('语音识别连接提前关闭'))
        }, { once: true })
        socket.addEventListener('message', (event) => {
          let payload: VoiceEvent
          try {
            payload = JSON.parse(String(event.data)) as VoiceEvent
          } catch {
            reject(new Error('语音服务返回了无法识别的数据'))
            return
          }
          if (payload.type === 'ready') {
            window.clearTimeout(timeout)
            resolve()
          } else if (payload.type === 'error') {
            reject(new Error(payload.message ?? '音频识别失败'))
          }
        })
      })

      hooks.onStatus('正在识别音频…')
      for (let offset = 0; offset < samples.length; offset += 1_600) {
        if (isAborted()) throw new DOMException('音频识别已取消', 'AbortError')
        if (socket.readyState !== WebSocket.OPEN) throw new Error('语音识别连接提前关闭')
        socket.send(pcm16(samples.subarray(offset, offset + 1_600)))
        await new Promise(resolve => window.setTimeout(resolve, 100))
      }
      socket.send(JSON.stringify({ type: 'commit' }))

      const result = await new Promise<VoiceFileTranscriptionResult>((resolve, reject) => {
        timeout = window.setTimeout(() => reject(new Error('等待最终转写超时')), 30_000)
        const onAbort = (): void => reject(new DOMException('音频识别已取消', 'AbortError'))
        signal?.addEventListener('abort', onAbort, { once: true })
        const onMessage = (event: MessageEvent): void => {
          let payload: VoiceEvent
          try {
            payload = JSON.parse(String(event.data)) as VoiceEvent
          } catch {
            return
          }
          if (payload.type === 'partial' && payload.text) hooks.onPartial(payload.text)
          if (payload.type === 'final' && payload.text) {
            finalText = payload.text.trim()
            elapsedMs = payload.elapsedMs ?? elapsedMs
            hooks.onPartial(finalText)
          }
          if (payload.type === 'done') {
            socket.removeEventListener('message', onMessage)
            signal?.removeEventListener('abort', onAbort)
            if (finalText === '') reject(new Error('音频中未识别到可发送的文字'))
            else resolve({ text: finalText, elapsedMs })
          }
          if (payload.type === 'error') {
            socket.removeEventListener('message', onMessage)
            signal?.removeEventListener('abort', onAbort)
            reject(new Error(payload.message ?? '音频识别失败'))
          }
        }
        socket.addEventListener('message', onMessage)
      })
      settled = true
      cleanup(false)
      return result
    } catch (error) {
      settled = true
      cleanup(true)
      throw error
    }
  }
}
