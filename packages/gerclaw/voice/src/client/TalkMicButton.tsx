/** Qianwen realtime microphone and audio-upload controls for the native composer. */
import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import type { InjectFace, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { TalkInterruptResult } from '../wire.ts'

export interface TalkMicInjected {
  interrupt: () => Promise<TalkInterruptResult>
}

export type TalkMicProps = PropsRuntime<'conversation.input.left'> & InjectFace<TalkMicInjected>

type BrowserVoiceEvent = {
  type?: 'ready' | 'partial' | 'final' | 'done' | 'error'
  text?: string
  message?: string
  elapsedMs?: number
}

interface RecordingResources {
  socket: WebSocket
  stream: MediaStream
  context: AudioContext
  source: MediaStreamAudioSourceNode
  processor: AudioWorkletNode
  sink: GainNode
  stopTimer: number
  flush: () => Promise<void>
}

const PCM_WORKLET = `
class GerclawPcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = new Float32Array(4096)
    this.offset = 0
    this.port.onmessage = (event) => {
      if (!event.data || event.data.type !== 'flush') return
      if (this.offset > 0) {
        const tail = this.buffer.slice(0, this.offset)
        this.port.postMessage(tail, [tail.buffer])
        this.buffer = new Float32Array(4096)
        this.offset = 0
      }
      this.port.postMessage({ type: 'flushed' })
    }
  }
  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0]
    if (input && input.length) {
      let cursor = 0
      while (cursor < input.length) {
        const count = Math.min(input.length - cursor, this.buffer.length - this.offset)
        this.buffer.set(input.subarray(cursor, cursor + count), this.offset)
        cursor += count
        this.offset += count
        if (this.offset === this.buffer.length) {
          this.port.postMessage(this.buffer, [this.buffer.buffer])
          this.buffer = new Float32Array(4096)
          this.offset = 0
        }
      }
    }
    const output = outputs[0] && outputs[0][0]
    if (output) output.fill(0)
    return true
  }
}
registerProcessor('gerclaw-pcm-processor', GerclawPcmProcessor)
`

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

const socketUrl = (sessionId: string): string => {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/gerclaw/api/voice/asr-stream?sessionId=${encodeURIComponent(sessionId)}`
}

/**
 * Composer microphone derived from dsh-talk@0.1.3. It deliberately has no
 * Web Speech fallback: captured/decoded PCM always reaches the account-local
 * Qianwen provider through the authenticated gateway.
 */
export function TalkMicButton({ interrupt, inputActions, sessionId }: TalkMicProps): ReactNode {
  const [phase, setPhase] = useState<'idle' | 'connecting' | 'recording' | 'uploading' | 'finishing' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const resources = useRef<RecordingResources | null>(null)
  const uploadSocket = useRef<WebSocket | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const finishing = useRef(false)
  const operationToken = useRef(0)
  // The native composer can replace its blank-session shell with the real
  // session shell while ASR is still streaming. Socket callbacks must always
  // address the latest DSH action face instead of the one captured at connect.
  const inputActionsRef = useRef(inputActions)
  inputActionsRef.current = inputActions

  const releaseRecording = async (): Promise<void> => {
    const current = resources.current
    resources.current = null
    if (current === null) return
    window.clearTimeout(current.stopTimer)
    current.processor.disconnect()
    current.sink.disconnect()
    current.source.disconnect()
    current.stream.getTracks().forEach((track) => { track.stop() })
    await current.context.close().catch(() => {})
  }

  const cancel = async (): Promise<void> => {
    operationToken.current += 1
    finishing.current = false
    const socket = resources.current?.socket ?? uploadSocket.current
    if (socket?.readyState === WebSocket.OPEN)
      socket.send(JSON.stringify({ type: 'cancel' }))
    socket?.close(1000)
    uploadSocket.current = null
    await releaseRecording()
    setMessage('已取消录音')
    setPhase('idle')
  }

  useEffect(() => () => {
    const current = resources.current
    resources.current = null
    if (current !== null) {
      window.clearTimeout(current.stopTimer)
      if (current.socket.readyState === WebSocket.OPEN)
        current.socket.send(JSON.stringify({ type: 'cancel' }))
      current.socket.close(1000)
      current.processor.disconnect()
      current.sink.disconnect()
      current.source.disconnect()
      current.stream.getTracks().forEach((track) => { track.stop() })
      void current.context.close().catch(() => {})
    }
    uploadSocket.current?.close(1000)
    uploadSocket.current = null
  }, [])

  const openSocket = (): Promise<WebSocket> => new Promise((resolve, reject) => {
    const socket = new WebSocket(socketUrl(String(sessionId)))
    socket.binaryType = 'arraybuffer'
    let settled = false
    const timeout = window.setTimeout(() => {
      socket.close()
      reject(new Error('语音识别服务连接超时'))
    }, 15_000)
    socket.addEventListener('error', () => {
      if (!settled) {
        window.clearTimeout(timeout)
        settled = true
        reject(new Error('无法连接语音识别服务'))
      }
    })
    socket.addEventListener('message', (event) => {
      let payload: BrowserVoiceEvent
      try {
        payload = JSON.parse(String(event.data)) as BrowserVoiceEvent
      } catch {
        setMessage('语音服务返回了无法识别的数据')
        setPhase('error')
        return
      }
      if (payload.type === 'ready' && !settled) {
        window.clearTimeout(timeout)
        settled = true
        resolve(socket)
      } else if (payload.type === 'partial' && payload.text) {
        inputActionsRef.current.setDraft(payload.text)
        setMessage(`正在识别：${payload.text}`)
      } else if (payload.type === 'final' && payload.text) {
        const text = payload.text.trim()
        inputActionsRef.current.setDraft(text)
        setMessage(`已完成转写 · ${((payload.elapsedMs ?? 0) / 1000).toFixed(2)} 秒`)
        if (text && finishing.current) {
          window.requestAnimationFrame(() => { inputActionsRef.current.submit() })
        }
      } else if (payload.type === 'done') {
        finishing.current = false
        uploadSocket.current = null
        setPhase('idle')
        socket.close(1000)
      } else if (payload.type === 'error') {
        const reason = payload.message ?? '语音识别失败'
        if (!settled) {
          window.clearTimeout(timeout)
          settled = true
          reject(new Error(reason))
        }
        setMessage(reason)
        setPhase('error')
      }
    })
  })

  const start = async (): Promise<void> => {
    const token = ++operationToken.current
    setPhase('connecting')
    setMessage('正在连接语音识别…')
    window.dispatchEvent(new CustomEvent('gerclaw:voice-interrupt'))
    await interrupt().catch(() => ({ stopped: false }))
    let pendingSocket: WebSocket | null = null
    let pendingStream: MediaStream | null = null
    let pendingContext: AudioContext | null = null
    try {
      pendingSocket = await openSocket()
      if (token !== operationToken.current) throw new DOMException('录音已取消', 'AbortError')
      pendingStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } })
      if (token !== operationToken.current) throw new DOMException('录音已取消', 'AbortError')
      pendingContext = new AudioContext()
      const socket = pendingSocket
      const stream = pendingStream
      const context = pendingContext
      const source = context.createMediaStreamSource(stream)
      const moduleUrl = URL.createObjectURL(new Blob([PCM_WORKLET], { type: 'text/javascript' }))
      try {
        await context.audioWorklet.addModule(moduleUrl)
      } finally {
        URL.revokeObjectURL(moduleUrl)
      }
      const processor = new AudioWorkletNode(context, 'gerclaw-pcm-processor', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
      })
      const sink = context.createGain()
      sink.gain.value = 0
      let flushResolve: (() => void) | undefined
      processor.port.onmessage = (event) => {
        if (typeof event.data === 'object' && event.data !== null && 'type' in event.data && event.data.type === 'flushed') {
          flushResolve?.()
          flushResolve = undefined
          return
        }
        if (socket.readyState !== WebSocket.OPEN) return
        if (!(event.data instanceof Float32Array)) return
        socket.send(pcm16(resample(event.data, context.sampleRate)))
      }
      source.connect(processor)
      processor.connect(sink)
      sink.connect(context.destination)
      await context.resume()
      if (token !== operationToken.current) throw new DOMException('录音已取消', 'AbortError')
      const flush = () => new Promise<void>((resolve) => {
        const timer = window.setTimeout(resolve, 1_000)
        flushResolve = () => {
          window.clearTimeout(timer)
          resolve()
        }
        processor.port.postMessage({ type: 'flush' })
      })
      const stopTimer = window.setTimeout(() => { void finish() }, 60_000)
      resources.current = { socket, stream, context, source, processor, sink, stopTimer, flush }
      pendingSocket = null
      pendingStream = null
      pendingContext = null
      setPhase('recording')
      setMessage('正在聆听，点击停止后发送')
    } catch (error) {
      pendingSocket?.close(1000)
      pendingStream?.getTracks().forEach((track) => { track.stop() })
      await pendingContext?.close().catch(() => {})
      await releaseRecording()
      if (token === operationToken.current) {
        setPhase('error')
        setMessage(error instanceof Error ? error.message : '无法开始录音')
      }
    }
  }

  const finish = async (): Promise<void> => {
    const current = resources.current
    if (current === null) return
    finishing.current = true
    setPhase('finishing')
    setMessage('正在确认转写…')
    await current.flush()
    await releaseRecording()
    if (current.socket.readyState === WebSocket.OPEN)
      current.socket.send(JSON.stringify({ type: 'commit' }))
  }

  const upload = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file === undefined) return
    const token = ++operationToken.current
    setPhase('uploading')
    setMessage('正在处理音频…')
    window.dispatchEvent(new CustomEvent('gerclaw:voice-interrupt'))
    await interrupt().catch(() => ({ stopped: false }))
    let context: AudioContext | null = null
    let socket: WebSocket | null = null
    try {
      context = new AudioContext()
      const decoded = await context.decodeAudioData(await file.arrayBuffer())
      if (token !== operationToken.current) throw new DOMException('音频上传已取消', 'AbortError')
      if (decoded.duration > 60.001) throw new Error('音频不能超过 60 秒')
      socket = await openSocket()
      if (token !== operationToken.current) throw new DOMException('音频上传已取消', 'AbortError')
      uploadSocket.current = socket
      const mono = new Float32Array(decoded.length)
      for (let channel = 0; channel < decoded.numberOfChannels; channel += 1) {
        const values = decoded.getChannelData(channel)
        for (let index = 0; index < mono.length; index += 1)
          mono[index] = (mono[index] ?? 0) + (values[index] ?? 0) / decoded.numberOfChannels
      }
      const samples = resample(mono, decoded.sampleRate)
      for (let offset = 0; offset < samples.length; offset += 1_600) {
        if (token !== operationToken.current) throw new DOMException('音频上传已取消', 'AbortError')
        if (socket.readyState !== WebSocket.OPEN) throw new Error('语音识别连接提前关闭')
        socket.send(pcm16(samples.subarray(offset, offset + 1_600)))
        await new Promise(resolve => window.setTimeout(resolve, 100))
      }
      await context.close()
      context = null
      finishing.current = true
      setPhase('finishing')
      setMessage('音频已上传，正在确认转写…')
      socket.send(JSON.stringify({ type: 'commit' }))
    } catch (error) {
      socket?.close()
      uploadSocket.current?.close()
      uploadSocket.current = null
      if (token === operationToken.current) {
        setPhase('error')
        setMessage(error instanceof Error ? error.message : '音频识别失败')
      }
    } finally {
      await context?.close().catch(() => {})
    }
  }

  return (
    <span data-gerclaw-voice-controls style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <button
        type="button"
        data-dsh-talk-mic
        data-recording={phase === 'recording' ? 'true' : 'false'}
        aria-label={phase === 'recording' ? '停止录音并发送' : '开始语音输入'}
        title={phase === 'recording' ? '停止录音并发送' : '语音输入'}
        disabled={phase === 'connecting' || phase === 'uploading' || phase === 'finishing'}
        onClick={() => { void (phase === 'recording' ? finish() : start()) }}
      >
        {phase === 'recording' ? '■' : '🎙'}
      </button>
      <button
        type="button"
        aria-label="上传音频进行识别"
        title="上传音频"
        disabled={phase !== 'idle' && phase !== 'error'}
        onClick={() => fileInput.current?.click()}
      >
        ♫
      </button>
      {(phase === 'recording' || phase === 'connecting' || phase === 'uploading' || phase === 'finishing') && (
        <button type="button" aria-label="取消语音输入" title="取消语音输入" onClick={() => { void cancel() }}>×</button>
      )}
      <input ref={fileInput} type="file" accept="audio/*" hidden onChange={(event) => { void upload(event) }} />
      {message && <span role="status" aria-live="polite" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>{message}</span>}
    </span>
  )
}
