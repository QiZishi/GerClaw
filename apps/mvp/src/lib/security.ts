/**
 * 医疗安全工具函数（占位实现）
 * 对齐 gerclaw设计要求.md §9.2 合规要求 / 铁律5 医疗安全底线 / 铁律6 循证可溯源
 * 注意：UI 壳子阶段（0001）为占位实现，0002 起接入真实后处理逻辑
 */
import { HIGH_RISK_SYMPTOMS, MEDICAL_DISCLAIMER } from "./constants";

/** 追加免责声明（§9.2） */
export function appendDisclaimer(text: string): string {
  if (text.includes(MEDICAL_DISCLAIMER)) return text;
  return `${text}\n\n---\n${MEDICAL_DISCLAIMER}`;
}

/**
 * 拦截确定性诊断用语（铁律5）
 * 替换"诊断为X"为"疑似X，建议进一步检查"
 */
const DETERMINISTIC_PATTERNS: { pattern: RegExp; replacement: string }[] = [
  {
    pattern: /诊断为(?!疑似)/g,
    replacement: "疑似",
  },
  {
    pattern: /确诊为/g,
    replacement: "考虑为",
  },
  {
    pattern: /确定是/g,
    replacement: "可能是",
  },
];

export function interceptDeterministicDiagnosis(text: string): string {
  let result = text;
  for (const { pattern, replacement } of DETERMINISTIC_PATTERNS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

/** 检测高风险症状，返回是否需要立即就医提示 */
export function detectHighRiskSymptoms(text: string): {
  hasHighRisk: boolean;
  matchedSymptoms: string[];
} {
  const matched: string[] = [];
  for (const symptom of HIGH_RISK_SYMPTOMS) {
    if (text.includes(symptom)) {
      matched.push(symptom);
    }
  }
  return {
    hasHighRisk: matched.length > 0,
    matchedSymptoms: matched,
  };
}

/** 高风险就医提示 */
export const EMERGENCY_ALERT =
  "⚠️ 您描述的症状可能较为紧急，建议立即就医或拨打 120。";

/** 输入安全过滤（占位，0002 起接入真实过滤） */
export function filterInput(input: string): { safe: boolean; filtered: string } {
  // UI 壳子阶段：仅做长度检查，不过滤内容
  return { safe: true, filtered: input };
}

/** PHI 脱敏占位（0002 起接入正则+NER） */
export function desensitizePHI(text: string): string {
  // UI 壳子阶段：不脱敏，原样返回
  return text;
}
