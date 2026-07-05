/**
 * CGA 老年综合评估类型定义
 * 对齐 gerclaw设计要求.md §7 老年综合评估模块
 */

/** 题目类型 */
export type QuestionType =
  | "single-choice" // 单选
  | "multiple-choice" // 多选
  | "scale" // 量表评分（1-5 等）
  | "text" // 文本输入
  | "voice"; // 语音输入

/** 选项 */
export interface ScaleOption {
  value: number;
  label: string;
  description?: string;
}

/** 题目 */
export interface ScaleQuestion {
  id: string;
  index: number;
  text: string;
  type: QuestionType;
  options?: ScaleOption[];
  maxValue?: number;
  /** 语音朗读文本（可不同于题目文字） */
  voiceText?: string;
  /** 跳转逻辑：根据答案跳到指定题目索引 */
  jumpLogic?: Record<string, number>;
  /** 是否必答 */
  required?: boolean;
  /** 提示 */
  hint?: string;
}

/** 量表 */
export interface Scale {
  id: string;
  name: string;
  fullName: string;
  description: string;
  category: string;
  questionCount: number;
  estimatedMinutes: number;
  questions: ScaleQuestion[];
  /** 分级阈值 */
  grading: {
    thresholds: { max: number; level: string; interpretation: string }[];
  };
}

/** 量表评估结果 */
export interface ScaleResult {
  scaleId: string;
  scaleName: string;
  totalScore: number;
  maxScore: number;
  level: string;
  interpretation: string;
  answers: Record<string, number | string>;
  completedAt: number;
}

/** CGA 综合评估报告 */
export interface CGAReport {
  id: string;
  sessionId: string;
  patientName?: string;
  patientAge?: number;
  createdAt: number;
  scaleResults: ScaleResult[];
  summary: string;
  recommendations: string[];
  riskLevel: "low" | "moderate" | "high";
  disclaimer: string;
}

/** CGA 评估状态 */
export type CGAStage =
  | "selecting"
  | "answering"
  | "completed"
  | "reporting"
  | "failed";

/** CGA 评估进度（用于右侧面板） */
export interface CGAProgress {
  stage: CGAStage;
  currentScale?: Scale;
  currentIndex: number;
  answers: Record<string, number | string>;
  completedScales: ScaleResult[];
  totalScales: number;
}
