/** One user-visible step in a GerClaw medical task. */
export interface TaskStep {
  /** Chinese step label. */
  name: string
  /** Current terminal or running state. */
  status: 'pending' | 'running' | 'completed' | 'failed'
  /** ISO timestamp at step start. */
  startedAt?: string
  /** ISO timestamp at step end. */
  endedAt?: string
  /** Wall-clock duration in milliseconds. */
  elapsedMs?: number
  /** Redacted user-facing key result. */
  summary?: string
}

/** One account-bound exported medical artifact. */
export interface ArtifactDescriptor {
  /** Unguessable artifact identifier inside the current account Host. */
  artifactId: string
  /** Task that owns this artifact. */
  taskId: string
  /** Native DSH session that owns this artifact. */
  sessionId?: string
  /** Download filename. */
  name: string
  /** Stable path relative to the current account's native DSH Workspace. */
  workspaceRef: string
  /** Normalized export format. */
  format: 'md' | 'html' | 'docx' | 'pdf' | 'png' | 'jpg' | 'json'
  /** HTTP media type. */
  mediaType: string
  /** Byte size. */
  size: number
  /** ISO creation timestamp. */
  createdAt: string
}

/** JSON-safe value stored in GerClaw task events and sent over DSH Remote. */
export type GerclawJsonValue =
  | null
  | boolean
  | number
  | string
  | GerclawJsonValue[]
  | { [key: string]: GerclawJsonValue }

/** Restorable medical task state displayed in one DSH conversation. */
export interface TaskRun {
  /** Stable task identifier. */
  taskId: string
  /** Native DSH session owning the task. */
  sessionId?: string
  /** GerClaw business operation. */
  kind: string
  /** Current task state. */
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  /** ISO start timestamp. */
  startedAt: string
  /** ISO end timestamp for a terminal task. */
  endedAt?: string
  /** Total duration in milliseconds. */
  elapsedMs?: number
  /** User-visible task steps. */
  steps: TaskStep[]
  /** Redacted key results. */
  keyResults: string[]
  /** Normalized JSON business result. */
  result?: GerclawJsonValue
  /** Generated account-bound artifacts. */
  artifacts: ArtifactDescriptor[]
  /** User-actionable error without stack or internals. */
  error?: string
}

/** Medical task kinds exposed to the GerClaw browser through DSH Remote. */
export type MedicalTaskKind =
  | 'profile'
  | 'cga'
  | 'medication'
  | 'chronic'
  | 'companion'
  | 'evidence'

/** Typed request used to submit one GerClaw medical task. */
export interface MedicalTaskSubmitRequest {
  /** Browser-generated id used for cancellation while the call is in flight. */
  requestId: string
  /** Medical plugin operation to run. */
  kind: MedicalTaskKind
  /** JSON-only business input interpreted by the selected medical plugin. */
  input: GerclawJsonValue
}

/** Typed result returned after a medical task reaches a terminal state. */
export interface MedicalTaskSubmitResult {
  /** Persisted task reconstructed from the native session event. */
  task: TaskRun
  /** JSON-only normalized business response rendered by the client. */
  response: GerclawJsonValue
}

/** Request for a persisted task owned by the current account Host. */
export interface MedicalTaskStatusRequest {
  /** Stable task id returned by submit. */
  taskId: string
}

/** Result of reading a task from the account-local medical store. */
export interface MedicalTaskStatusResult {
  /** Persisted task, or null when it does not exist in this account Host. */
  task: TaskRun | null
}

/** Request to cancel one in-flight medical task in this browser session. */
export interface MedicalTaskCancelRequest {
  /** Browser-generated request id supplied to submit. */
  requestId: string
}

/** Cancellation acknowledgement without leaking internal controller state. */
export interface MedicalTaskCancelResult {
  /** True only when an active task was found and interrupted. */
  cancelled: boolean
  /** Stable task id when an active task was found. */
  taskId?: string
}

/** Request to export one persisted task in selected supported formats. */
export interface MedicalTaskExportRequest {
  /** Stable task id owned by this account Host. */
  taskId: string
  /** Unique export formats generated from the same normalized result. */
  formats: Array<'md' | 'html' | 'docx' | 'pdf' | 'png' | 'jpg' | 'json'>
}

/** Typed export result consumed by the GerClaw artifact sidebar. */
export interface MedicalTaskExportResult {
  /** Account-bound descriptors for newly generated files. */
  artifacts: ArtifactDescriptor[]
}
