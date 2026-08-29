/** Replaceable GerClaw medical-task runtime and durable event vocabulary. */
import { Context, Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import type { ArtifactDescriptor, ArtifactFormat } from '@gerclaw/artifact'

export type { ArtifactDescriptor, ArtifactFormat } from '@gerclaw/artifact'

export interface TaskStep {
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  startedAt?: string
  endedAt?: string
  elapsedMs?: number
  summary?: string
}

export type GerclawJsonValue = null | boolean | number | string | GerclawJsonValue[] | {
  [key: string]: GerclawJsonValue
}

export interface TaskRun {
  taskId: string
  sessionId?: string
  kind: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  startedAt: string
  endedAt?: string
  elapsedMs?: number
  steps: TaskStep[]
  keyResults: string[]
  result?: GerclawJsonValue
  artifacts: ArtifactDescriptor[]
  error?: string
}

export type MedicalTaskKind = 'profile' | 'cga' | 'medication' | 'chronic' | 'companion' | 'evidence'

export interface MedicalTaskSubmitRequest {
  requestId: string
  kind: MedicalTaskKind
  input: GerclawJsonValue
}

export interface MedicalTaskSubmitResult { task: TaskRun; response: GerclawJsonValue }
export interface MedicalTaskStatusRequest { taskId: string }
export interface MedicalTaskStatusResult { task: TaskRun | null }
export interface MedicalTaskCancelRequest { requestId: string }
export interface MedicalTaskCancelResult { cancelled: boolean; taskId?: string }
export interface MedicalTaskExportRequest { taskId: string; formats: ArtifactFormat[] }
export interface MedicalTaskExportResult { artifacts: ArtifactDescriptor[] }

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
