/** Click-to-speak action for one finalized native DSH assistant message. */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'

type Props = PropsRuntime<'conversation.chat.assistant-actions'>

const SpeakerIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 10v4h4l5 4V6L8 10H4Z" />
    <path d="M16 9.5a4 4 0 0 1 0 5M18.5 7a7.5 7.5 0 0 1 0 10" />
  </svg>
)
type AudioLine = {
  type?: 'meta' | 'audio' | 'done'
  audio?: string
  sampleRate?: number
  elapsedMs?: number
}

interface Playback {
  owner: string
  lease: symbol
  controller: AbortController
  context: AudioContext
  sources: Set<AudioBufferSourceNode>
  next: number
  onStopped: () => void
}

let active: Playback | null = null
const isActive = (playback: Playback): boolean => active === playback

const stopActive = async (): Promise<void> => {
  const playback = active
  active = null
  if (playback === null) return
  playback.controller.abort()
  for (const source of playback.sources) {
    try { source.stop() } catch {}
  }
  playback.sources.clear()
  await playback.context.close().catch(() => {})
  playback.onStopped()
}

/** Stop the current Qianwen playback from another composer control. */
export function interruptPlayback(): void {
  void stopActive()
}

export function installPlaybackInterruption(): () => void {
  const interrupt = interruptPlayback
  const interruptOnComposerInput = (event: Event): void => {
    if (event.target instanceof HTMLTextAreaElement
      || event.target instanceof HTMLInputElement
      || (event.target instanceof HTMLElement && event.target.isContentEditable)) interrupt()
  }
  window.addEventListener('gerclaw:voice-interrupt', interrupt)
  document.addEventListener('input', interruptOnComposerInput, true)
  return () => {
    window.removeEventListener('gerclaw:voice-interrupt', interrupt)
    document.removeEventListener('input', interruptOnComposerInput, true)
    interruptPlayback()
  }
}

const assistantText = (snapshot: ConversationSnapshot, messageId: string): string => {
  const nodes = (snapshot as unknown as {
    chat: { nodes: { values: () => ReadonlyArray<{ kind: string; data: unknown }> } }
  }).chat.nodes.values()
  for (const node of nodes) {
    if (node.kind !== 'assistant-step') continue
    const data = node.data as {
      finalNode?: { messageId?: string; blocks?: ReadonlyArray<{ kind?: string; text?: string }> }
    }
    if (data.finalNode?.messageId !== messageId) continue
    return (data.finalNode.blocks ?? [])
      .filter(block => block.kind === 'text')
      .map(block => block.text ?? '')
      .join('')
      .trim()
  }
  return ''
}

const queuePcm = (playback: Playback, base64: string, sampleRate: number): void => {
  const raw = atob(base64)
  const bytes = Uint8Array.from(raw, character => character.charCodeAt(0))
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const count = Math.floor(bytes.byteLength / 2)
  const buffer = playback.context.createBuffer(1, count, sampleRate)
  const channel = buffer.getChannelData(0)
  for (let index = 0; index < count; index += 1)
    channel[index] = view.getInt16(index * 2, true) / 32_768
  const source = playback.context.createBufferSource()
  source.buffer = buffer
  source.connect(playback.context.destination)
  playback.sources.add(source)
  source.addEventListener('ended', () => playback.sources.delete(source))
  playback.next = Math.max(playback.next, playback.context.currentTime + 0.04)
  source.start(playback.next)
  playback.next += buffer.duration
}

export function TalkMessageButton({ messageId, useSession, sessionId }: Props): ReactNode {
  const text = useSession(snapshot => assistantText(snapshot, String(messageId)))
  const owner = `${String(sessionId)}:${String(messageId)}`
  const lease = useRef(Symbol('gerclaw-tts-lease'))
  const mounted = useRef(true)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle')
  const [error, setError] = useState('')

  useEffect(() => {
    mounted.current = true
    if (active?.owner === owner) {
      active.lease = lease.current
      active.onStopped = () => { if (mounted.current) setPhase('idle') }
      setPhase('playing')
    }
    return () => {
      mounted.current = false
      const expectedLease = lease.current
      window.setTimeout(() => {
        if (active?.lease === expectedLease) void stopActive()
      }, 50)
    }
  }, [owner])

  const speak = async (): Promise<void> => {
    if (!text) return
    await stopActive()
    const controller = new AbortController()
    const context = new AudioContext({ sampleRate: 24_000 })
    const playback: Playback = {
      owner,
      lease: lease.current,
      controller,
      context,
      sources: new Set(),
      next: context.currentTime,
      onStopped: () => { if (mounted.current) setPhase('idle') },
    }
    active = playback
    setError('')
    setPhase('loading')
    try {
      const response = await fetch('/gerclaw/api/voice/tts', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-gerclaw-session-id': String(sessionId),
        },
        body: JSON.stringify({
          text,
          voice: localStorage.getItem('gerclaw.voice') ?? 'Cherry',
        }),
        signal: controller.signal,
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { error?: string }
        throw new Error(payload.error ?? '朗读服务暂时不可用')
      }
      if (response.body === null) throw new Error('朗读服务没有返回音频')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let pending = ''
      let sampleRate = 24_000
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        pending += decoder.decode(value, { stream: true })
        const lines = pending.split('\n')
        pending = lines.pop() ?? ''
        for (const line of lines) {
          if (!line) continue
          const event = JSON.parse(line) as AudioLine
          if (event.type === 'meta' && event.sampleRate) sampleRate = event.sampleRate
          if (event.type === 'audio' && event.audio) {
            queuePcm(playback, event.audio, sampleRate)
            setPhase('playing')
          }
        }
      }
      const waitMs = Math.max(0, (playback.next - context.currentTime) * 1_000)
      await new Promise(resolve => window.setTimeout(resolve, waitMs + 80))
      if (isActive(playback)) await stopActive()
      setPhase('idle')
    } catch (reason) {
      if (controller.signal.aborted) {
        setPhase('idle')
        return
      }
      if (isActive(playback)) await stopActive()
      setError(reason instanceof Error ? reason.message : '朗读失败')
      setPhase('error')
    }
  }

  const playing = phase === 'loading' || phase === 'playing'
  return (
    <button
      type="button"
      data-gerclaw-read-aloud
      aria-label={playing ? '停止朗读' : phase === 'error' ? `重新朗读，刚才失败：${error}` : '朗读这条回复'}
      title={playing ? '停止朗读' : phase === 'error' ? error : '朗读'}
      disabled={!text}
      onClick={() => { void (playing ? stopActive().then(() => { setPhase('idle') }) : speak()) }}
    >
      {phase === 'loading' ? '…' : <SpeakerIcon />}
    </button>
  )
}
