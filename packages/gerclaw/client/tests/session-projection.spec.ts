import { describe, expect, it } from 'vitest'
import type {} from '../src/index.ts'
import type {} from '../../voice/src/speech.ts'
import {
  applyPrescriptionIntakeProjection,
  initPrescriptionIntakeProjection,
} from '../src/projection.ts'
import {
  applyGerclawVoiceProjection,
  initGerclawVoiceProjection,
} from '../../voice/src/projection.ts'

describe('GerClaw session projections', () => {
  it('folds prescription and voice events and ignores unrelated events', () => {
    const intake = {
      version: 1 as const,
      status: 'collecting' as const,
      healthGoal: '控制血压',
      documentRefs: [],
      conversationTurns: 1,
      missingFields: ['currentConcerns' as const],
      nextQuestion: '目前最困扰您的症状、问题或检查异常是什么？',
      updatedAt: '2026-08-25T00:00:00.000Z',
    }
    const intakeEvent = {
      type: 'gerclaw/prescription-intake', seq: 3, time: 0,
      data: { version: 1 as const, turn: null, intake },
    } as const
    const initialIntake = initPrescriptionIntakeProjection()
    expect(applyPrescriptionIntakeProjection(initialIntake, intakeEvent)).toEqual(intake)
    const unrelated = { type: 'turn/start', seq: 4, time: 0, data: { turn: 1 } } as const
    const afterIntake = applyPrescriptionIntakeProjection(intake, unrelated)
    expect(afterIntake).toBe(intake)

    const voiceEvent = {
      type: 'gerclaw/voice', seq: 6, time: 0,
      data: { version: 1 as const, kind: 'asr' as const, status: 'completed' as const,
        model: 'qwen3-asr-flash-realtime', text: '控制血压', elapsedMs: 50 },
    } as const
    expect(applyGerclawVoiceProjection(initGerclawVoiceProjection(), voiceEvent)).toEqual({
      seq: 6, ...voiceEvent.data,
    })
  })
})
