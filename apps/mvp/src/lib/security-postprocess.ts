/**
 * 医疗安全后处理
 * 对齐铁律5：禁止确定性诊断，高风险症状提示立即就医
 * 免责声明由UI层统一显示（MessageBubble底部/ChatInput底部），此处不再追加文本
 */

const SUICIDE_RISK_ALERT =
  "⚠️ 如果您有伤害自己的想法，请立即拨打心理危机干预热线：北京 010-82951332，全国 24 小时热线：400-161-9995。请告诉您的家人或医生。";

const DISCLAIMER_PATTERNS = [
  /内容由\s*AI\s*生成[，,。.\s]*仅供参考[，,。.\s]*身体不适请及时就医[。.]?\s*$/g,
  /以上建议仅供参考[，,。.\s]*身体不适请及时就医[。.]?\s*$/g,
  /AI辅助建议[，,。.\s]*需结合临床判断[。.]?\s*$/g,
  /以上仅供参考[，,。.\s]*不能替代线下就医[。.]?\s*$/g,
  /本平台仅供健康咨询参考[，,。.\s]*不能替代线下就医[。.]?\s*$/g,
  /\n{2,}内容由\s*AI\s*生成[\s\S]*$/g,
];

interface DiagnosticPattern {
  pattern: RegExp;
  replacement: (...args: string[]) => string;
}

const DIAGNOSTIC_PATTERNS: DiagnosticPattern[] = [
  {
    pattern: /确诊为(.+?)([。，！？,\.\s]|$)/g,
    replacement: (_m, disease, end) =>
      `提示${disease}可能性，需医生进一步检查${end === "。" || end === "." ? "。" : end}`,
  },
  {
    pattern: /你得了(.+?)(病)?([。，！？,\.\s]|$)/g,
    replacement: (_m, disease, _bing, end) =>
      `可能是${disease}，建议就医确诊${end === "。" || end === "." ? "。" : end}`,
  },
  {
    pattern: /肯定是(.+?)(病)?([。，！？,\.\s]|$)/g,
    replacement: (_m, thing, _bing, end) =>
      `提示${thing}可能性，需医生进一步检查${end === "。" || end === "." ? "。" : end}`,
  },
  {
    pattern: /一定是(.+?)(病)?([。，！？,\.\s]|$)/g,
    replacement: (_m, thing, _bing, end) =>
      `提示${thing}可能性，需医生进一步检查${end === "。" || end === "." ? "。" : end}`,
  },
  {
    pattern: /就是(.+?)病([。，！？,\.\s]|$)/g,
    replacement: (_m, disease, end) =>
      `提示${disease}可能性，需医生进一步检查${end === "。" || end === "." ? "。" : end}`,
  },
];

function replaceDiagnosticLanguage(text: string): string {
  let result = text;
  for (const { pattern, replacement } of DIAGNOSTIC_PATTERNS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

function stripModelGeneratedDisclaimer(text: string): string {
  let result = text.trim();
  for (const pattern of DISCLAIMER_PATTERNS) {
    result = result.replace(pattern, "").trim();
  }
  return result;
}

function prependSuicideAlert(text: string): string {
  if (text.includes(SUICIDE_RISK_ALERT)) return text;
  return `${SUICIDE_RISK_ALERT}\n\n${text}`;
}

export function postprocessMedicalText(
  text: string,
  options?: { isEmergency?: boolean; isSuicideRisk?: boolean }
): string {
  let result = text;

  result = replaceDiagnosticLanguage(result);

  result = stripModelGeneratedDisclaimer(result);

  if (options?.isSuicideRisk) {
    result = prependSuicideAlert(result);
  }

  return result;
}
