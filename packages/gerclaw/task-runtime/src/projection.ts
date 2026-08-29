/** Replayable GerClaw medical-task session projection. */
import { z } from 'zod'
import type { SessionEvent } from '@deepseek-ai/dsh-session/types'
import type { TaskRun } from './index.ts'

export type TaskProjectionState = TaskRun | null

const taskStepSchema = z.object({
  name: z.string(),
  status: z.enum(['pending', 'running', 'completed', 'failed']),
  startedAt: z.string().optional(),
  endedAt: z.string().optional(),
  elapsedMs: z.number().nonnegative().optional(),
  summary: z.string().optional(),
})

const artifactSchema = z.object({
  artifactId: z.string(),
  taskId: z.string(),
  sessionId: z.string().optional(),
  name: z.string(),
  workspaceRef: z.string(),
  format: z.enum(['md', 'html', 'docx', 'pdf', 'png', 'jpg', 'json']),
  mediaType: z.string(),
  size: z.number().nonnegative(),
  createdAt: z.string(),
})

const taskSchema = z.object({
  taskId: z.string(),
  sessionId: z.string(),
  kind: z.string(),
  status: z.enum(['running', 'completed', 'failed', 'cancelled']),
  startedAt: z.string(),
  endedAt: z.string().optional(),
  elapsedMs: z.number().nonnegative().optional(),
  steps: z.array(taskStepSchema),
  keyResults: z.array(z.string()),
  result: z.unknown().optional(),
  artifacts: z.array(artifactSchema),
  error: z.string().optional(),
})

export const taskProjectionSchema = z.union([taskSchema, z.null()]) as z.ZodType<TaskProjectionState>

export function initTaskProjection(): TaskProjectionState {
  return null
}

export function applyTaskProjection(state: TaskProjectionState, event: SessionEvent): TaskProjectionState {
  if (event.type !== 'gerclaw/task') return state
  return event.data.task
}

export const TASK_PROJECTION_STATE_VERSION = 1

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionMap {
    'gerclaw/task': TaskProjectionState
  }
  interface SessionProjectionStateMap {
    'gerclaw/task': TaskProjectionState
  }
}
