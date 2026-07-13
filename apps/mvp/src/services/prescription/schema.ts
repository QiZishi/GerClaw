import { z } from "zod";

const MEDICAL_DISCLAIMER = "⚠️ 免责声明：本处方由AI系统生成，仅供健康参考，不能替代专业医生的诊断和治疗建议。如有不适，请及时就医，遵医嘱调整用药和治疗方案。";

export const HealthProfileSchema = z.object({
  summary: z.string().min(1, "健康画像总结不能为空"),
  mainIssues: z.array(z.string()).min(1, "主要健康问题不能为空"),
  riskAssessment: z.string().min(1, "风险评估不能为空"),
});

export const ExercisePrescriptionSchema = z.object({
  recommendation: z.string().min(1, "运动建议不能为空"),
  intensity: z.string().min(1, "运动强度不能为空"),
  frequency: z.string().min(1, "运动频率不能为空"),
  precautions: z.array(z.string()).min(1, "注意事项不能为空"),
});

export const NutritionPrescriptionSchema = z.object({
  recommendation: z.string().min(1, "营养建议不能为空"),
  dietaryPrinciples: z.array(z.string()).min(1, "饮食原则不能为空"),
  sampleMeal: z.string().min(1, "示例食谱不能为空"),
  precautions: z.array(z.string()).min(1, "注意事项不能为空"),
});

export const PsychologyPrescriptionSchema = z.object({
  assessment: z.string().min(1, "心理评估不能为空"),
  interventions: z.array(z.string()).min(1, "干预措施不能为空"),
  referralSuggestion: z.string().min(1, "转诊建议不能为空"),
});

export const MedicationPrescriptionSchema = z.object({
  currentMeds: z.array(z.string()).min(1, "当前用药不能为空"),
  interactions: z.array(z.string()),
  highRiskWarnings: z.array(z.string()).optional(),
  suggestions: z.array(z.string()).min(1, "用药建议不能为空"),
  precautions: z.array(z.string()).min(1, "注意事项不能为空"),
});

export const SmokingAlcoholPrescriptionSchema = z.object({
  smokingStatus: z.string().min(1, "吸烟情况不能为空"),
  alcoholStatus: z.string().min(1, "饮酒情况不能为空"),
  advice: z.array(z.string()).min(1, "戒烟限酒建议不能为空"),
});

export const PrescriptionOutputSchema = z.object({
  healthProfile: HealthProfileSchema,
  exercisePrescription: ExercisePrescriptionSchema,
  nutritionPrescription: NutritionPrescriptionSchema,
  psychologyPrescription: PsychologyPrescriptionSchema,
  medicationPrescription: MedicationPrescriptionSchema,
  smokingAlcoholPrescription: SmokingAlcoholPrescriptionSchema,
  disclaimer: z.string().default(MEDICAL_DISCLAIMER),
});

export type PrescriptionOutputType = z.infer<typeof PrescriptionOutputSchema>;

export function parsePrescriptionJSON(text: string): { success: true; data: PrescriptionOutputType } | { success: false; error: string } {
  try {
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return { success: false, error: "未找到JSON数据" };
    }
    const jsonStr = jsonMatch[0];
    const parsed = JSON.parse(jsonStr);
    const result = PrescriptionOutputSchema.safeParse(parsed);
    if (!result.success) {
      const errors = result.error.issues.map(i => `${i.path.join(".")}: ${i.message}`).join("; ");
      return { success: false, error: `JSON校验失败: ${errors}` };
    }
    if (!result.data.disclaimer || !result.data.disclaimer.includes("免责声明") && !result.data.disclaimer.includes("仅供") && !result.data.disclaimer.includes("不能替代")) {
      result.data.disclaimer = MEDICAL_DISCLAIMER;
    }
    return { success: true, data: result.data };
  } catch (e) {
    return { success: false, error: `JSON解析失败: ${e instanceof Error ? e.message : String(e)}` };
  }
}

export const PRESCRIPTION_JSON_SYSTEM_PROMPT = `你是GerClaw老年科AI助手，请严格按照以下JSON Schema输出结构化的五大处方数据，不要输出其他解释性文字，只输出纯JSON：

{
  "healthProfile": {
    "summary": "患者基本情况总结（100-200字）",
    "mainIssues": ["主要健康问题1", "主要健康问题2", "..."],
    "riskAssessment": "风险评估（包括跌倒风险、用药风险、营养风险等）"
  },
  "exercisePrescription": {
    "recommendation": "具体运动建议",
    "intensity": "运动强度（如中等强度、低强度）",
    "frequency": "运动频率（如每周3-5次，每次30分钟）",
    "precautions": ["注意事项1", "注意事项2", "..."]
  },
  "nutritionPrescription": {
    "recommendation": "营养建议",
    "dietaryPrinciples": ["饮食原则1", "饮食原则2", "..."],
    "sampleMeal": "示例食谱",
    "precautions": ["注意事项1", "注意事项2", "..."]
  },
  "psychologyPrescription": {
    "assessment": "心理状态评估",
    "interventions": ["干预措施1", "干预措施2", "..."],
    "referralSuggestion": "是否需要转诊及建议"
  },
  "medicationPrescription": {
    "currentMeds": ["当前用药1（名称+剂量+频次）", "当前用药2", "..."],
    "interactions": ["药物相互作用风险1", "药物相互作用风险2", "..."],
    "highRiskWarnings": ["⚠️ 高风险警告1", "⚠️ 高风险警告2", "..."],
    "suggestions": ["用药建议1", "用药建议2", "..."],
    "precautions": ["注意事项1", "注意事项2", "..."]
  },
  "smokingAlcoholPrescription": {
    "smokingStatus": "吸烟情况描述",
    "alcoholStatus": "饮酒情况描述",
    "advice": ["戒烟限酒建议1", "戒烟限酒建议2", "..."]
  },
  "disclaimer": "医疗免责声明"
}

重要要求：
1. 检查患者用药列表中是否存在明显的药物相互作用风险，如有必须在interactions中明确指出
2. 高风险用药警告（如多种降压药联用、抗凝药与其他药相互作用等）放在highRiskWarnings中，并以"⚠️"开头
3. 确保各处方之间一致，运动处方的强度要考虑患者心脏状况，营养处方要考虑糖尿病/肾病等合并症
4. 所有建议必须适合老年人，注意老年人的生理特点和用药安全
5. disclaimer必须包含医疗免责声明文字`;
