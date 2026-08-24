/** Replaceable GerClaw speech service definition. */
import type { IncomingMessage } from 'node:http'
import type { Duplex } from 'node:stream'
import { Context, Service } from '@deepseek-ai/cordis'

export const QIANWEN_ASR_MODEL = 'qwen3-asr-flash-realtime'
export const QIANWEN_TTS_MODEL = 'qwen3-tts-instruct-flash-realtime'

export interface SpeechProviderInfo {
  engine: 'qianwen'
  asrModel: typeof QIANWEN_ASR_MODEL
  ttsModel: typeof QIANWEN_TTS_MODEL
  defaultVoice: string
}

export interface SpeechAudioChunk {
  audio: Uint8Array
  sampleRate: 24000
  channels: 1
  encoding: 'pcm16le'
}

export interface GerclawVoiceEvent {
  version: 1
  kind: 'asr' | 'tts'
  status: 'completed' | 'interrupted' | 'failed'
  model: string
  text: string
  elapsedMs: number
  voice?: string | undefined
  interruptionReason?: 'user-cancelled' | 'new-input' | 'client-disconnected' | 'plugin-unloaded' | undefined
  error?: string | undefined
}

export type SpeechEventSink = (event: GerclawVoiceEvent) => void

declare module '@deepseek-ai/cordis' {
  interface Context {
    speech: SpeechProvider
  }
}

/** Provider seam consumed by the account-local voice interaction plugin. */
export abstract class SpeechProvider extends Service {
  constructor(ctx: Context) {
    super(ctx, 'speech')
  }

  abstract readonly info: SpeechProviderInfo

  abstract acceptAsrUpgrade(
    req: IncomingMessage,
    socket: Duplex,
    head: Buffer,
    emit: SpeechEventSink,
  ): void

  abstract synthesizeStream(
    text: string,
    signal?: AbortSignal,
    requestedVoice?: string,
  ): AsyncGenerator<SpeechAudioChunk>
}

export default SpeechProvider
