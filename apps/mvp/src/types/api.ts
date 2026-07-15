/**
 * API 请求/响应类型定义
 * 对齐 gerclaw设计要求.md §4.16 前后端通信协议
 * 所有信任边界响应仍需由对应 services/BFF 的 Zod schema 在运行时校验。
 */

/** SSE 流式事件类型（§4.16.3 前端渲染对应关系） */
export type SSEEventType =
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "agent_start"
  | "text_delta"
  | "asr_result"
  | "prescription_progress"
  | "prescription_result"
  | "search_result"
  | "file_status"
  | "done"
  | "error";

/** SSE 事件基础结构 */
export interface SSEEvent<T = unknown> {
  event: SSEEventType;
  data: T;
  timestamp: number;
}

/** 对话请求（POST /api/chat） */
export interface ChatRequest {
  session_id: string;
  message: string;
  loaded_skills?: string[];
  uploaded_files?: string[];
}

/** 语音对话请求（POST /api/chat/voice） */
export interface VoiceChatRequest {
  session_id: string;
  format: "wav" | "mp3";
}

/** 五大处方生成请求（POST /api/prescriptions/generate） */
export interface PrescriptionRequest {
  session_id: string;
  patient_info: Record<string, unknown>;
}

/** ASR 结果事件 data */
export interface ASRResultData {
  text: string;
  confidence: number;
}

/** 处方进度事件 data */
export interface PrescriptionProgressData {
  step: "collecting" | "generating" | "validating" | "exporting";
  collected?: number;
  total?: number;
  phase?: string;
}

/** API 错误 */
export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
  retriable?: boolean;
}

/** 统一 API 响应 */
export interface ApiResponse<T> {
  ok: boolean;
  data?: T;
  error?: ApiError;
}
