import assert from "node:assert/strict";
import test from "node:test";

import { fivePrescriptionDraftToMarkdown } from "./prescription-report.ts";
import type { FivePrescriptionDraft } from "./schemas.ts";

const evidence = [{ evidence_id: "ev_local1234", title: "本地指南", source: "local", locator: "第 1 节", url: null }];
const recommendation = [{ content: "建议项目", evidence_ids: ["ev_local1234"] }];
const baseSection = { goal: "共同目标", recommendations: recommendation, precautions: ["共同注意事项"], evidence_ids: ["ev_local1234"] };

const draft: FivePrescriptionDraft = {
  template_version: "five-prescription-report-v1",
  model_output_schema_version: "five-prescription-model-output-v1",
  status: "needs_clinician_review",
  patient_summary: { age: 72, sex: "female", health_goals: ["改善耐力"], current_concerns: ["近期跌倒"] },
  health_assessment: { summary: "评估摘要", key_issues: ["重点问题"], risk_factors: ["跌倒风险"], clinician_review_required: true },
  medication: { ...baseSection, kind: "medication", title: "药物处方", medication_items: ["既往用药"], monitoring_requirements: ["监测血压"], review_required: true },
  exercise: { ...baseSection, kind: "exercise", title: "运动处方", contraindications: ["运动禁忌核对"], phases: [{ name: "起步", duration: "两周", intensity: "低强度", instructions: "循序渐进" }] },
  nutrition: { ...baseSection, kind: "nutrition", title: "营养处方", assessment_summary: "营养评估", target_energy_kcal: 1800, target_protein_g: 60, monitoring: ["监测体重"] },
  psychological: { ...baseSection, kind: "psychological", title: "心理处方", assessment_summary: "心理评估", follow_up: "随访心理状态", review_required: true },
  rehabilitation: { ...baseSection, kind: "rehabilitation", title: "康复处方", rehabilitation_type: "平衡训练", functional_assessment: "功能评估", training_plan: ["训练安排"], assistive_devices: ["手杖核对"], safety_precautions: ["康复安全事项"] },
  medication_review: null,
  evidence_sources: evidence,
  uploaded_document_ids: ["6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911"],
  uploaded_image_evidence_ids: ["ev_img1234567890abcdef12345678"],
  disclaimer: "AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。",
};

test("keeps every structured five-prescription field in the exported report", () => {
  const content = fivePrescriptionDraftToMarkdown(draft);
  for (const expected of [
    "72 岁", "改善耐力", "近期跌倒", "跌倒风险", "既往用药", "监测血压",
    "## 药物处方", "## 运动处方", "## 营养处方", "## 心理处方", "## 康复处方",
    "运动禁忌核对", "1800 kcal", "60 g", "平衡训练", "功能评估", "手杖核对", "康复安全事项",
    "上传图片：本次使用 1 张病例图片", "章节依据：ev_local1234",
  ]) assert.ok(content.includes(expected), `export is missing ${expected}`);
});
