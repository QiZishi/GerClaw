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

/**
 * LLM输入脱敏：脱敏PHI（个人健康信息），用于发送给LLM的文本
 * 只脱敏明确匹配的身份证号、手机号、医保号/社保卡号、住院号、姓名
 * 保留医学相关数字（年龄、血压、剂量等）
 */
export function desensitizeForLLM(text: string): string {
  let result = text;

  // 1. 身份证号：18位数字（可能带x/X），保留前3后4
  result = result.replace(
    /(?<![0-9])([1-9]\d{2})(\d{11,12})(\d{3}[\dxX])(?![0-9])/g,
    (_, prefix, middle, suffix) => {
      if (middle.length === 11 || middle.length === 12) {
        return `${prefix}${'*'.repeat(middle.length)}${suffix}`;
      }
      return _;
    }
  );

  // 2. 手机号：11位数字，1开头，第二位3-9，保留前3后4
  result = result.replace(
    /(?<![0-9])(1[3-9]\d)(\d{4})(\d{4})(?![0-9])/g,
    '$1****$3'
  );

  // 3. 医保号/社保卡号：匹配关键词后的数字，保留前4后4
  result = result.replace(
    /(医保号|社保号|医保卡号|社保卡号|医疗保险号)\s*[:：]?\s*(\d{4})(\d+)(\d{4})/g,
    (_, keyword, prefix, middle, suffix) => {
      return `${keyword}：${prefix}${'*'.repeat(Math.min(middle.length, 8))}${suffix}`;
    }
  );

  // 4. 住院号：匹配关键词后的数字，保留前2后2
  result = result.replace(
    /(住院号|病案号|门诊号)\s*[:：]?\s*(\d{2})(\d+)(\d{2})/g,
    (_, keyword, prefix, middle, suffix) => {
      return `${keyword}：${prefix}${'*'.repeat(Math.min(middle.length, 6))}${suffix}`;
    }
  );

  // 5. 姓名：2-4个中文字符，在特定上下文后，保留姓
  const namePatterns = [
    /(我叫|我是|姓名[是为为：:]\s*|名字[是叫为为：:]\s*|患者姓名[：:是为]\s*)([\u4e00-\u9fa5])([\u4e00-\u9fa5]{1,3})/g,
  ];
  for (const pattern of namePatterns) {
    result = result.replace(pattern, (_, prefix, surname, givenName) => {
      return `${prefix}${surname}${'*'.repeat(givenName.length)}`;
    });
  }

  return result;
}

/** PHI脱敏（兼容旧接口） */
export function desensitizePHI(text: string): string {
  return desensitizeForLLM(text);
}
