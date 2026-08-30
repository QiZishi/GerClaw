/** Replaceable GerClaw medical-task runtime and durable event vocabulary. */
import { Context, Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {
  MedicalTaskCancelRequest,
  MedicalTaskCancelResult,
  MedicalTaskExportRequest,
  MedicalTaskExportResult,
  MedicalTaskStatusRequest,
  MedicalTaskStatusResult,
  MedicalTaskSubmitRequest,
  MedicalTaskSubmitResult,
  TaskRun,
} from './types.ts'

export type * from './types.ts'

export interface CompletedTaskInput {
  kind: string
  result: unknown
  steps: Array<{ name: string; summary: string; elapsedMs?: number }>
  taskId?: string
}

export {
  applyTaskProjection,
  initTaskProjection,
  taskProjectionSchema,
  TASK_PROJECTION_STATE_VERSION,
  type TaskProjectionState,
} from './projection.ts'

declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    /** Whole-value, replayable GerClaw medical task state. */
    'gerclaw/task': { version: 1; turn: null; task: TaskRun }
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context { gerclawTasks: GerclawTaskRuntime }
}

/** Account-local task seam backed by DSH Jobs, sessions, storage and artifacts. */
export abstract class GerclawTaskRuntime extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawTasks') }
  abstract submit(agent: Agent, request: MedicalTaskSubmitRequest, signal: AbortSignal): Promise<MedicalTaskSubmitResult>
  abstract cancel(agent: Agent, request: MedicalTaskCancelRequest): MedicalTaskCancelResult
  abstract status(agent: Agent, request: MedicalTaskStatusRequest): MedicalTaskStatusResult
  abstract export(agent: Agent, request: MedicalTaskExportRequest): Promise<MedicalTaskExportResult>
  abstract complete(agent: Agent, input: CompletedTaskInput): Promise<TaskRun>
}

export default GerclawTaskRuntime
