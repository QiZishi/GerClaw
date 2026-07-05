/**
 * 用药审查类型定义
 * 对齐 gerclaw设计要求.md §4.1 用药审查 + ADR-004（100%确定性规则引擎）
 */

/** 风险等级 */
export type RiskLevel =
  | "safe" // 安全
  | "caution" // 谨慎
  | "warning" // 警告
  | "contraindicated" // 禁忌
  | "severe"; // 严重

/** 药物条目 */
export interface DrugItem {
  id: string;
  name: string;
  genericName?: string;
  dosage?: string;
  frequency?: string;
  route?: string; // 给药途径
  /** 患者年龄/肾功能等用于剂量校验 */
  context?: {
    age?: number;
    renalFunction?: "normal" | "mild" | "moderate" | "severe";
  };
}

/** DDI 药物相互作用结果 */
export interface DDIResult {
  drugA: string;
  drugB: string;
  severity: RiskLevel;
  mechanism: string;
  clinicalEffect: string;
  recommendation: string;
  evidenceSource?: string;
}

/** Beers 标准结果（老年人潜在不适当用药） */
export interface BeersResult {
  drug: string;
  category: string;
  severity: RiskLevel;
  reason: string;
  recommendation: string;
  alternative?: string[];
}

/** 剂量校验结果 */
export interface DosageResult {
  drug: string;
  prescribedDose: string;
  recommendedRange: string;
  status: "ok" | "too-high" | "too-low" | "unknown";
  recommendation?: string;
}

/** 用药审查综合结果 */
export interface DrugReviewResult {
  id: string;
  sessionId: string;
  createdAt: number;
  drugs: DrugItem[];
  ddiResults: DDIResult[];
  beersResults: BeersResult[];
  dosageResults: DosageResult[];
  overallRisk: RiskLevel;
  summary: string;
  recommendations: string[];
  disclaimer: string;
}

/** 用药审查状态 */
export type DrugReviewStage =
  | "input"
  | "reviewing"
  | "done"
  | "failed";
