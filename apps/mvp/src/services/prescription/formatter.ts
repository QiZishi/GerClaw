import type { PrescriptionOutputType } from "./schema";

export function formatPrescriptionToMarkdown(data: PrescriptionOutputType): string {
  const sections: string[] = [];

  sections.push(`# 老年综合评估五大处方报告\n`);

  sections.push(`## 一、健康画像\n`);
  sections.push(`### 基本情况总结\n${data.healthProfile.summary}\n`);
  sections.push(`### 主要健康问题\n`);
  data.healthProfile.mainIssues.forEach((issue, i) => {
    sections.push(`${i + 1}. ${issue}`);
  });
  sections.push(``);
  sections.push(`### 风险评估\n${data.healthProfile.riskAssessment}\n`);

  sections.push(`---\n`);

  if (data.medicationPrescription.highRiskWarnings && data.medicationPrescription.highRiskWarnings.length > 0) {
    sections.push(`<div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; margin: 16px 0; border-radius: 0 8px 8px 0;">\n`);
    sections.push(`### ⚠️ 高风险用药警告\n`);
    data.medicationPrescription.highRiskWarnings.forEach(w => {
      sections.push(`- ${w}`);
    });
    sections.push(`\n</div>\n`);
  }

  sections.push(`## 二、运动处方\n`);
  sections.push(`### 运动建议\n${data.exercisePrescription.recommendation}\n`);
  sections.push(`### 运动强度\n${data.exercisePrescription.intensity}\n`);
  sections.push(`### 运动频率\n${data.exercisePrescription.frequency}\n`);
  sections.push(`### 注意事项\n`);
  data.exercisePrescription.precautions.forEach((p, i) => {
    sections.push(`${i + 1}. ${p}`);
  });
  sections.push(``);

  sections.push(`---\n`);

  sections.push(`## 三、营养处方\n`);
  sections.push(`### 营养建议\n${data.nutritionPrescription.recommendation}\n`);
  sections.push(`### 饮食原则\n`);
  data.nutritionPrescription.dietaryPrinciples.forEach((p, i) => {
    sections.push(`${i + 1}. ${p}`);
  });
  sections.push(``);
  sections.push(`### 示例食谱\n${data.nutritionPrescription.sampleMeal}\n`);
  sections.push(`### 注意事项\n`);
  data.nutritionPrescription.precautions.forEach((p, i) => {
    sections.push(`${i + 1}. ${p}`);
  });
  sections.push(``);

  sections.push(`---\n`);

  sections.push(`## 四、心理处方\n`);
  sections.push(`### 心理状态评估\n${data.psychologyPrescription.assessment}\n`);
  sections.push(`### 干预措施\n`);
  data.psychologyPrescription.interventions.forEach((p, i) => {
    sections.push(`${i + 1}. ${p}`);
  });
  sections.push(``);
  sections.push(`### 转诊建议\n${data.psychologyPrescription.referralSuggestion}\n`);

  sections.push(`---\n`);

  sections.push(`## 五、用药处方\n`);
  sections.push(`### 当前用药\n`);
  data.medicationPrescription.currentMeds.forEach((m, i) => {
    sections.push(`${i + 1}. ${m}`);
  });
  sections.push(``);
  if (data.medicationPrescription.interactions.length > 0) {
    sections.push(`### 药物相互作用提示\n`);
    data.medicationPrescription.interactions.forEach((p) => {
      sections.push(`- ${p}`);
    });
    sections.push(``);
  }
  sections.push(`### 用药建议\n`);
  data.medicationPrescription.suggestions.forEach((p, i) => {
    sections.push(`${i + 1}. ${p}`);
  });
  sections.push(``);
  sections.push(`### 注意事项\n`);
  data.medicationPrescription.precautions.forEach((p, i) => {
    sections.push(`${i + 1}. ${p}`);
  });
  sections.push(``);

  sections.push(`---\n`);

  sections.push(`## 六、戒烟限酒处方\n`);
  sections.push(`### 吸烟情况\n${data.smokingAlcoholPrescription.smokingStatus}\n`);
  sections.push(`### 饮酒情况\n${data.smokingAlcoholPrescription.alcoholStatus}\n`);
  sections.push(`### 建议\n`);
  data.smokingAlcoholPrescription.advice.forEach((p, i) => {
    sections.push(`${i + 1}. ${p}`);
  });
  sections.push(``);

  sections.push(`---\n`);
  sections.push(data.disclaimer);

  return sections.join("\n");
}

export function formatHealthProfileMarkdown(data: {
  summary: string;
  mainIssues: string[];
  riskAssessment: string;
}): string {
  const sections: string[] = [];
  sections.push(`## 健康画像\n`);
  sections.push(`**基本情况总结**\n\n${data.summary}\n`);
  sections.push(`**主要健康问题**\n`);
  data.mainIssues.forEach((issue, i) => {
    sections.push(`${i + 1}. ${issue}`);
  });
  sections.push(``);
  sections.push(`**风险评估**\n\n${data.riskAssessment}\n`);
  return sections.join("\n");
}

export function createEmptyPrescriptionInput(): import("@/types/prescription").PrescriptionInput {
  return {
    basicInfo: {},
    healthOverview: {},
    medications: { inpatient: [], discharge: [] },
    examReports: {},
    medicalRecords: {},
    lifestyle: {},
    rawText: "",
  };
}
