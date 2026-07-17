/**
 * 对话相关类型定义
 * 对齐 gerclaw设计要求.md §4.1 通用对话 / §4.2.3 可视化 / §3.3 主聊天区
 */

/** 消息角色 */
export type MessageRole = "user" | "assistant" | "system";

/** 消息状态 */
export type MessageStatus = "streaming" | "done" | "error" | "stopped" | "interrupted";

/** 工具调用状态 */
export type ToolCallStatus = "running" | "done" | "failed";

/** 思维链状态 */
export type ThinkingStatus = "thinking" | "done";

/** 决策步骤状态 */
export type DecisionStepStatus = "running" | "done" | "failed";

/** 简化步骤状态（用于SimpleStepIndicator） */
export type SimpleStepStatus = "pending" | "running" | "done";

/** 简化步骤图标类型 */
export type SimpleStepIcon = "thinking" | "search" | "answering";

/** 简化步骤（思考中→搜索中→回答中） */
export interface SimpleStepData {
  id: string;
  label: string;
  status: SimpleStepStatus;
  icon: SimpleStepIcon;
}

/** 文件上传/解析状态 */
export type FileStatus = "uploading" | "parsing" | "done" | "failed";

/** 角色（医生/患者/访客） */
export type Role = "patient" | "doctor" | "visitor";

/** 主题 */
export type Theme = "light" | "dark" | "system";

/** 模型调用协议 */
export type ModelProtocol = "openai" | "dashscope" | "anthropic";

/** 模型优先级 */
export type ModelPreference = "primary" | "backup1" | "backup2";

/** 引用来源 */
export interface Citation {
  id: number;
  title: string;
  snippet: string;
  url: string;
  source: string;
  publishedDate?: string;
}

/** 思维链块（§4.2.3 ThinkingBlock） */
export interface ThinkingBlock {
  id: string;
  content: string;
  status: ThinkingStatus;
  startedAt: number;
  endedAt?: number;
}

/** 工具调用块（§4.2.3 ToolCallBlock） */
export interface ToolCallBlock {
  id: string;
  toolCallId?: string;
  toolName: string;
  toolIcon?: string;
  params?: Record<string, unknown>;
  args?: Record<string, unknown>;
  result?: unknown;
  status: ToolCallStatus;
  errorMessage?: string;
  startedAt: number;
  endedAt?: number;
  durationMs?: number;
}

/** 子智能体节点（§4.2.3 SubAgentTree） */
export interface SubAgentNode {
  id: string;
  name: string;
  status: "running" | "done" | "failed";
  children?: SubAgentNode[];
  detail?: string;
  startedAt: number;
  endedAt?: number;
}

/** 决策步骤（§4.2.3 DecisionTimeline，ReAct Thought/Action/Observation） */
export interface DecisionStep {
  id: string;
  stepIndex: number;
  type: "thought" | "action" | "observation";
  title: string;
  content: string;
  status: DecisionStepStatus;
  durationMs?: number;
  timestamp: number;
}

/** 联网搜索结果（§4.2.3 SearchResultCard） */
export interface SearchResultItem {
  id: string;
  title: string;
  url: string;
  source: string;
  snippet: string;
  favicon?: string;
  publishedDate?: string;
}

/** 文件标签（§4.2.3 FileTag + DocumentToolCard） */
export interface FileTag {
  id: string;
  fileName: string;
  fileType: string;
  fileSize: number;
  status: FileStatus;
  progress?: number; // 0-100
  errorMessage?: string;
  thumbnailUrl?: string;
  parsedMarkdown?: string;
  /** 加密登记后的后端引用；正文始终只留在当前组件内存。 */
  serverDocumentId?: string;
  /** 登记时绑定的本地会话，切换会话后必须重新登记。 */
  documentSessionId?: string;
  /** 解析完成时间；未记录时 UI 不得用组件挂载时间冒充 */
  parsedAt?: number;
}

/** 图片附件 */
export interface ImageAttachment {
  mimeType: string;
  /** base64 数据（不含 data: 前缀） */
  base64: string;
  /** 文件名或 alt 文本 */
  alt?: string;
}

/** 信息收集字段 */
export interface InfoCollectionField {
  key: string;
  label: string;
  value?: string;
  filled: boolean;
}

/** 问题卡片中的单个问题 */
export interface QuestionItem {
  id: string;
  label: string;
  placeholder?: string;
  type: "text" | "textarea";
  required?: boolean;
}

/** 问题卡片数据（Trae Work风格对话卡片） */
export interface QuestionCardData {
  round: number;
  maxRounds: number;
  questions: QuestionItem[];
  answers: Record<string, string>;
  submitted?: boolean;
}

/** 阶段指示卡片 */
export interface StageIndicatorData {
  stage: "collecting" | "health_profile" | "generating";
  title: string;
  description?: string;
}

export interface RuntimeApprovalBlockData {
  approvalId: string;
  toolName: string;
  expiresAt: string;
  policyVersion: string;
  toolVersion: string;
}

/** Runtime Harness 确认的紧急医疗安全提示；前端不得自行推断或改写风险级别。 */
export interface EmergencyAlertBlockData {
  codes: string[];
  message: string;
}

/** 消息内容块（一条消息可包含多个块：文本/图片/思维链/工具调用/搜索结果/文件/决策/操作按钮/信息收集卡片/问题卡片/阶段指示） */
export type MessageBlock =
  | { kind: "text"; id: string; content: string; streaming?: boolean }
  | { kind: "image"; id: string; data: ImageAttachment }
  | { kind: "thinking"; id: string; data: ThinkingBlock }
  | { kind: "tool_call"; id: string; data: ToolCallBlock }
  | { kind: "sub_agent"; id: string; data: SubAgentNode }
  | { kind: "decision"; id: string; data: DecisionStep[] }
  | { kind: "search_results"; id: string; data: SearchResultItem[] }
  | { kind: "file"; id: string; data: FileTag }
  | { kind: "info_collection"; id: string; data: { fields: InfoCollectionField[] } }
  | { kind: "question_card"; id: string; data: QuestionCardData }
  | { kind: "stage_indicator"; id: string; data: StageIndicatorData }
  | { kind: "runtime_approval"; id: string; data: RuntimeApprovalBlockData }
  | { kind: "emergency_alert"; id: string; data: EmergencyAlertBlockData }
  | {
      kind: "action";
      id: string;
      /** 摘要文字 */
      summary: string;
      /** 按钮文字 */
      buttonLabel: string;
      /** 点击按钮触发的右侧面板类型 */
      panelType: RightPanelType;
    };

/** 消息 */
export interface Message {
  id: string;
  sessionId: string;
  role: MessageRole;
  blocks: MessageBlock[];
  citations?: Citation[];
  /** 简化步骤指示器状态（思考中→搜索中→回答中） */
  steps?: SimpleStepData[];
  status: MessageStatus;
  createdAt: number;
  /** 已加载技能ID列表 */
  loadedSkills?: string[];
  /** 已上传文件ID列表 */
  uploadedFiles?: string[];
  /** 生成这条消息的受治理对话模式；用于避免跨模式展示错误的安全文案。 */
  workflow?: "standard" | "companion";
  /** 是否含免责声明 */
  hasDisclaimer?: boolean;
  /**
   * 仅用于刚完成的一次回复的自动朗读信号。组件开始朗读后会立即消费，
   * 因此重新打开历史会话或刷新页面不会朗读旧消息。
   */
  autoTtsPending?: boolean;
  /** 服务端完成本次聊天执行后返回的 Trace ID；只允许用于同主体反馈。 */
  traceId?: string;
  /** 用户反馈 */
  feedback?: "up" | "down" | null;
  /** 反馈文字 */
  feedbackText?: string;
  /** 未知网络结果重试时复用，避免创建重复反馈。 */
  feedbackIdempotencyKey?: string;
}

/** 会话 */
export interface Session {
  id: string;
  title: string;
  role: Role;
  createdAt: number;
  updatedAt: number;
  pinned?: boolean;
  /** 最后一条消息预览 */
  lastMessagePreview?: string;
  /** 消息数 */
  messageCount: number;
  /** 该会话生成的结果类型（用于自动展开右侧面板）*/
  panelType?: RightPanelType;
  /** 与 panelType 配对的真实报告内容；禁止跨会话复用 */
  panelContent?: string;
}

/** 模型配置 */
export interface ModelConfig {
  url: string;
  apiKey: string;
  modelName: string;
  protocol: ModelProtocol;
  preference: ModelPreference;
}

/** 输入框上下文（标签区域：已加载技能/已上传文件） */
export interface InputContext {
  loadedSkillIds: string[];
  uploadedFileIds: string[];
}

/** 聊天中可加载的功能动作类型（在中间栏执行，非右侧面板）*/
export type ChatActionType =
  | "none"
  | "companion"
  | "prescription"
  | "cga"
  | "drug-review"
  | "chronic-care"
  | "health-profile";

/** 右侧面板类型 */
export type RightPanelType =
  | "skills"
  | "prescription"
  | "cga"
  | "file-preview"
  | "citations"
  | "health-profile"
  | "drug-review"
  | "doc-editor"
  | "settings"
  | null;
