/**
 * The `talk:speech` session-projection unit: a last-wins fold of
 * `dsh-talk/speech` events into one whole value per session. The web client's
 * session-scoped record button reads the value through `useProjection` and
 * plays each fresh Qianwen utterance (audio fetched through `talk/audio`).
 * Pure mathematics only — the
 * projection registry owns the drive and notification. Imports the pure
 * `/types` outlet of dsh-session (never its root), so the client program can
 * pull the `SessionProjectionMap` merge in without host `Context` merges.
 *
 * @module dsh-talk/projection
 */

import { z } from 'zod'
import type { SessionEvent } from '@deepseek-ai/dsh-session/types'
import type { GerclawVoiceEvent } from '@gerclaw/speech'
import type {} from './speech.ts'
import { talkSpeechProjectionSchema as talkSpeechValueSchema } from './vocabulary.ts'
import type { TalkSpeechProjection } from './vocabulary.ts'

export type { TalkSpeechProjection } from './vocabulary.ts'

/** State schema for the projection registry: the value or null before the first speech event. */
export const talkSpeechProjectionSchema = z.union([talkSpeechValueSchema, z.null()])

/** Unit state: the latest speech event, or null for an empty log. */
export type TalkSpeechProjectionState = TalkSpeechProjection | null

/** State for the empty log. */
export function initTalkSpeechProjection(): TalkSpeechProjectionState {
  return null
}

/**
 * Pure transition: a `dsh-talk/speech` event replaces the whole state; every
 * other event returns the same reference so the drive does zero work.
 *
 * @param state - the state covering all prior events.
 * @param event - the next committed session event.
 * @returns the next state (same reference when the event is not speech).
 */
export function applyTalkSpeechProjection(state: TalkSpeechProjectionState, event: SessionEvent): TalkSpeechProjectionState {
  const candidate = event as unknown as { seq: number; type: string; data: Partial<TalkSpeechProjection> }
  if (candidate.type !== 'dsh-talk/speech') return state
  if (typeof candidate.data.utteranceId !== 'string'
    || candidate.data.engine !== 'qianwen'
    || typeof candidate.data.text !== 'string'
    || typeof candidate.data.audioBytes !== 'number'
    || candidate.data.reason !== 'user-read-aloud') return state
  return {
    seq: candidate.seq,
    utteranceId: candidate.data.utteranceId,
    engine: candidate.data.engine,
    text: candidate.data.text,
    audioBytes: candidate.data.audioBytes,
    reason: candidate.data.reason,
    ...(candidate.data.error !== undefined ? { error: candidate.data.error } : {}),
    ...(candidate.data.interrupted === true ? { interrupted: true } : {}),
  }
}

/** State → wire payload (the state already matches the wire shape). */
export function viewTalkSpeechProjection(state: TalkSpeechProjectionState): TalkSpeechProjection | null {
  return state
}

/** Cache-invalidation version for the persisted projection cache. */
export const TALK_SPEECH_PROJECTION_STATE_VERSION = 1

/** Latest sanitized ASR/TTS outcome; audio and credentials never enter state. */
export type GerclawVoiceProjectionState = (GerclawVoiceEvent & { seq: number }) | null

const gerclawVoiceEventSchema = z.object({
  version: z.literal(1),
  kind: z.enum(['asr', 'tts']),
  status: z.enum(['completed', 'interrupted', 'failed']),
  model: z.string(),
  text: z.string(),
  elapsedMs: z.number().nonnegative(),
  voice: z.string().optional(),
  interruptionReason: z.enum(['user-cancelled', 'new-input', 'client-disconnected', 'plugin-unloaded']).optional(),
  error: z.string().optional(),
})

export const gerclawVoiceProjectionSchema = z.union([
  gerclawVoiceEventSchema.extend({ seq: z.number().int().nonnegative() }),
  z.null(),
])

export function initGerclawVoiceProjection(): GerclawVoiceProjectionState {
  return null
}

export function applyGerclawVoiceProjection(
  state: GerclawVoiceProjectionState,
  event: SessionEvent,
): GerclawVoiceProjectionState {
  if (event.type !== 'gerclaw/voice') return state
  return { seq: event.seq, ...event.data }
}

export function viewGerclawVoiceProjection(
  state: GerclawVoiceProjectionState,
): GerclawVoiceProjectionState {
  return state
}

export const GERCLAW_VOICE_PROJECTION_STATE_VERSION = 1

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionMap {
    'talk:speech': TalkSpeechProjection | null
  }
  interface SessionProjectionStateMap {
    'talk:speech': TalkSpeechProjectionState
    'gerclaw/voice': GerclawVoiceProjectionState
  }
  interface SessionProjectionMap {
    'gerclaw/voice': GerclawVoiceProjectionState
  }
}
