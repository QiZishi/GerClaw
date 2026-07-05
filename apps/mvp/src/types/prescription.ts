/**
 * 五大处方类型定义
 * 对齐 gerclaw设计要求.md §6 五大处方模块
 * 模板路径：/Users/qizs/conclusion/gerclaw/输入输出/五大处方报告模板.md
 */

/** 处方类别 */
export type PrescriptionType =
  | "drug" // 药物处方
  | "exercise" // 运动处方
  | "nutrition" // 营养处方
  | "psychology" // 心理处方
  | "rehabilitation"; // 康复处方

/** 循证来源 */
export interface EvidenceSource {
  title: string;
  url?: string;
  snippet?: string;
  publishedDate?: string;
}

/** 处方条目（单条建议） */
export interface PrescriptionItem {
  name: string;
  detail: string;
  dosage?: string; // 药物剂量
  frequency?: string; // 频次
  duration?: string; // 疗程
  precautions?: string[]; // 注意事项
  evidence?: EvidenceSource[]; // 循证来源
}

/** 单类处方 */
export interface PrescriptionSection {
  type: PrescriptionType;
  title: string;
  summary: string;
  items: PrescriptionItem[];
  evidence: EvidenceSource[];
}

/** 患者信息摘要 */
export interface PatientSummary {
  name?: string;
  age?: number;
  gender?: "male" | "female";
  chiefComplaint?: string;
  history?: string[];
  allergies?: string[];
  currentMedications?: string[];
  vitals?: Record<string, string>;
}

/** 健康诊断 */
export interface HealthDiagnosis {
  summary: string;
  problems: string[];
  suspectedDiagnoses: string[]; // 注意：禁止确定性诊断，仅"疑似"
  riskFactors: string[];
}

/** 五大处方报告（结构化 JSON，对齐 §6.1 模板规范） */
export interface PrescriptionReport {
  id: string;
  sessionId: string;
  createdAt: number;
  patient: PatientSummary;
  diagnosis: HealthDiagnosis;
  sections: PrescriptionSection[];
  citations: EvidenceSource[];
  disclaimer: string;
}

/** 处方生成阶段 */
export type PrescriptionStage =
  | "idle"
  | "collecting"
  | "completing"
  | "generating"
  | "validating"
  | "done"
  | "failed";

/** 信息收集字段定义 */
export interface PrescriptionField {
  key: string;
  label: string;
  type: "text" | "number" | "select" | "textarea" | "date";
  required: boolean;
  options?: string[];
  placeholder?: string;
  value?: unknown;
  filled?: boolean;
}

/** 处方生成状态（用于右侧面板向导） */
export interface PrescriptionState {
  stage: PrescriptionStage;
  collectedFields: PrescriptionField[];
  totalFields: number;
  filledFields: number;
  currentReport?: PrescriptionReport;
  errorMessage?: string;
  /** 信息补全对话轮次（上限10轮） */
  completingTurns: number;
}

/** 导出格式 */
export type ExportFormat = "markdown" | "pdf" | "docx";
