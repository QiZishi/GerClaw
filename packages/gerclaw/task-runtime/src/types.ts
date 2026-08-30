/** Transport-safe GerClaw medical task protocol. */
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
