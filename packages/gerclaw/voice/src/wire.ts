/** Qianwen-only Remote wire contract inherited from dsh-talk's typed face. */
import { z } from 'zod'
import type { InvocationDescriptor } from '@deepseek-ai/dsh-typert-protocol'

export interface TalkStatus {
  stt: { engine: 'qianwen'; model: 'qwen3-asr-flash-realtime'; language: string }
  tts: { engine: 'qianwen'; model: 'qwen3-tts-instruct-flash-realtime'; voice: string }
  record: { enabled: boolean; hotkey: string | null; maxSeconds: 60 }
  interrupt: boolean
}

export const TALK_STATUS_SCHEMA = z.object({
  stt: z.object({
    engine: z.literal('qianwen'),
    model: z.literal('qwen3-asr-flash-realtime'),
    language: z.string(),
  }),
  tts: z.object({
    engine: z.literal('qianwen'),
    model: z.literal('qwen3-tts-instruct-flash-realtime'),
    voice: z.string(),
  }),
  record: z.object({
    enabled: z.boolean(),
    hotkey: z.string().nullable(),
    maxSeconds: z.literal(60),
  }),
  interrupt: z.boolean(),
})

export interface TalkAudio {
  utteranceId: string
  mime: 'audio/L16;rate=24000;channels=1'
  data: string
  text: string
  engine: 'qianwen'
}

export const TALK_AUDIO_SCHEMA = z.object({
  utteranceId: z.string(),
  mime: z.literal('audio/L16;rate=24000;channels=1'),
  data: z.string(),
  text: z.string(),
  engine: z.literal('qianwen'),
})

export interface TalkInterruptResult { stopped: boolean }
export const TALK_INTERRUPT_RESULT_SCHEMA = z.object({ stopped: z.boolean() })

const SOURCE = Object.freeze({ file: 'src/wire.ts', line: 1, column: 1 })

export const TALK_STATUS_DESCRIPTOR = Object.freeze({
  id: 'dsh-talk#talk/status',
  service: 'talk',
  namespace: 'talk',
  method: 'status',
  invocation: Object.freeze({ kind: 'direct' }),
  parameters: Object.freeze([]),
  result: Object.freeze({
    mode: 'strict',
    typeSymbol: 'dsh-talk/types#TalkStatus',
    schema: TALK_STATUS_SCHEMA,
  }),
  sourceLocation: SOURCE,
} as const) satisfies InvocationDescriptor

export const TALK_AUDIO_DESCRIPTOR = Object.freeze({
  id: 'dsh-talk#talk/audio',
  service: 'talk',
  namespace: 'talk',
  method: 'audio',
  invocation: Object.freeze({ kind: 'direct' }),
  parameters: Object.freeze([Object.freeze({
    name: 'utteranceId',
    wire: 'utteranceId',
    source: 'json',
    codec: Object.freeze({
      mode: 'strict',
      typeSymbol: 'dsh-talk/types#TalkAudioUtteranceId',
      schema: z.string(),
    }),
  } satisfies InvocationDescriptor['parameters'][number])]),
  result: Object.freeze({
    mode: 'strict',
    typeSymbol: 'dsh-talk/types#TalkAudio',
    schema: z.union([TALK_AUDIO_SCHEMA, z.null()]),
  }),
  sourceLocation: SOURCE,
} as const) satisfies InvocationDescriptor

export const TALK_INTERRUPT_DESCRIPTOR = Object.freeze({
  id: 'dsh-talk#talk/interrupt',
  service: 'talk',
  namespace: 'talk',
  method: 'interrupt',
  invocation: Object.freeze({ kind: 'direct' }),
  parameters: Object.freeze([]),
  result: Object.freeze({
    mode: 'strict',
    typeSymbol: 'dsh-talk/types#TalkInterruptResult',
    schema: TALK_INTERRUPT_RESULT_SCHEMA,
  }),
  sourceLocation: SOURCE,
} as const) satisfies InvocationDescriptor

export const TALK_INVOCATIONS = Object.freeze([
  TALK_STATUS_DESCRIPTOR,
  TALK_AUDIO_DESCRIPTOR,
  TALK_INTERRUPT_DESCRIPTOR,
])
