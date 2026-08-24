/** Shared, secret-free GerClaw voice event vocabulary. */
import { z } from 'zod'

export type SpeechReason = 'user-read-aloud'
export type SpeechTtsEngine = 'qianwen'

export interface DshTalkSpeechEvent {
  kind: 'tts'
  utteranceId: string
  engine: 'qianwen'
  text: string
  audioBytes: number
  reason: SpeechReason
  error?: string | undefined
  interrupted?: boolean | undefined
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

export interface TalkSpeechProjection {
  seq: number
  utteranceId: string
  engine: 'qianwen'
  text: string
  audioBytes: number
  reason: SpeechReason
  error?: string | undefined
  interrupted?: boolean | undefined
}

export const talkSpeechProjectionSchema = z.object({
  seq: z.number().int(),
  utteranceId: z.string(),
  engine: z.literal('qianwen'),
  text: z.string(),
  audioBytes: z.number().int(),
  reason: z.literal('user-read-aloud'),
  error: z.string().optional(),
  interrupted: z.boolean().optional(),
})
