/** Replayable GerClaw prescription-intake session projection. */
import { z } from 'zod'
import type { SessionEvent } from '@deepseek-ai/dsh-session/types'
import type { PrescriptionIntakeState } from '@gerclaw/prescription'

export type PrescriptionIntakeProjectionState = PrescriptionIntakeState | null

const prescriptionIntakeSchema = z.object({
  version: z.literal(1),
  status: z.enum(['collecting', 'information_complete', 'limit_reached', 'completed']),
  healthGoal: z.string().optional(),
  currentConcerns: z.string().optional(),
  currentMedications: z.string().optional(),
  documentRefs: z.array(z.string()),
  conversationTurns: z.number().int().nonnegative(),
  missingFields: z.array(z.enum(['healthGoal', 'currentConcerns'])),
  nextQuestion: z.string().optional(),
  updatedAt: z.string(),
})

export const prescriptionIntakeProjectionSchema = z.union([
  prescriptionIntakeSchema,
  z.null(),
]) as unknown as z.ZodType<PrescriptionIntakeProjectionState>

export function initPrescriptionIntakeProjection(): PrescriptionIntakeProjectionState {
  return null
}

export function applyPrescriptionIntakeProjection(
  state: PrescriptionIntakeProjectionState,
  event: SessionEvent,
): PrescriptionIntakeProjectionState {
  if (event.type !== 'gerclaw/prescription-intake') return state
  return event.data.intake
}

export const PRESCRIPTION_INTAKE_PROJECTION_STATE_VERSION = 1

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionMap {
    'gerclaw/prescription-intake': PrescriptionIntakeProjectionState
  }
  interface SessionProjectionStateMap {
    'gerclaw/prescription-intake': PrescriptionIntakeProjectionState
  }
}
