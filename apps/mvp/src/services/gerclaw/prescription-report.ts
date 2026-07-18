import type { FivePrescriptionDraft } from "./schemas";

type DraftSection =
  | FivePrescriptionDraft["medication"]
  | FivePrescriptionDraft["exercise"]
  | FivePrescriptionDraft["nutrition"]
  | FivePrescriptionDraft["psychological"]
  | FivePrescriptionDraft["rehabilitation"];

/**
 * Keep the side-panel/export artifact derived only from the validated API
 * response.  This never invents a report or turns the draft into an order.
 */
export function fivePrescriptionDraftToMarkdown(draft: FivePrescriptionDraft): string {
  const bullets = (items: readonly string[], empty: string) =>
    items.length > 0 ? items.map((item) => `- ${item}`) : [`- ${empty}`];
  const section = (title: string, value: DraftSection) => [
    `## ${title}`,
    `**目标：** ${value.goal}`,
    "",
    "### 建议（待临床复核）",
    ...value.recommendations.flatMap((item) => [
      `- ${item.content}（依据：${item.evidence_ids.join("、")}）`,
    ]),
    "",
    "### 注意事项",
    ...value.precautions.map((item) => `- ${item}`),
    "",
    `章节依据：${value.evidence_ids.join("、")}`,
    "",
  ];
  const medication = [
    ...section(draft.medication.title, draft.medication),
    "### 已记录的用药信息（需核对）",
    ...bullets(draft.medication.medication_items, "未记录具体用药信息。"),
    "",
    "### 用药核对与监测重点",
    ...(draft.medication.monitoring_requirements.length > 0
      ? draft.medication.monitoring_requirements.map((item) => `- ${item}`)
      : ["- 未提供额外监测事项；请由医生或药师核对。"]),
    "",
  ];
  const exercise = [
    ...section(draft.exercise.title, draft.exercise),
    "### 不适合运动或需先确认的情况",
    ...bullets(draft.exercise.contraindications, "未提供额外禁忌信息，开始前请由临床人员核对。"),
    "",
    "### 运动阶段",
    ...draft.exercise.phases.flatMap((phase) => [
      `- **${phase.name}**（${phase.duration}；${phase.intensity}）：${phase.instructions}`,
    ]),
    "",
  ];
  const nutrition = [
    ...section(draft.nutrition.title, draft.nutrition),
    `### 营养评估\n${draft.nutrition.assessment_summary}`,
    "",
    "### 供专业人员核对的营养目标",
    ...(draft.nutrition.target_energy_kcal === null
      ? ["- 未提供能量目标。"]
      : [`- 能量：${draft.nutrition.target_energy_kcal} kcal`]),
    ...(draft.nutrition.target_protein_g === null
      ? ["- 未提供蛋白质目标。"]
      : [`- 蛋白质：${draft.nutrition.target_protein_g} g`]),
    "",
    "### 营养监测重点",
    ...draft.nutrition.monitoring.map((item) => `- ${item}`),
    "",
  ];
  const psychological = [
    ...section(draft.psychological.title, draft.psychological),
    `### 评估摘要\n${draft.psychological.assessment_summary}`,
    "",
    `### 后续复核\n- ${draft.psychological.follow_up}`,
    "",
  ];
  const rehabilitation = [
    ...section(draft.rehabilitation.title, draft.rehabilitation),
    `### 康复类型\n${draft.rehabilitation.rehabilitation_type}`,
    "",
    `### 功能评估\n${draft.rehabilitation.functional_assessment}`,
    "",
    "### 训练计划",
    ...draft.rehabilitation.training_plan.map((item) => `- ${item}`),
    "",
    "### 辅助器具建议",
    ...bullets(draft.rehabilitation.assistive_devices, "未提出辅助用具建议。"),
    "",
    "### 康复安全注意事项",
    ...draft.rehabilitation.safety_precautions.map((item) => `- ${item}`),
    "",
  ];
  const medicationReview = draft.medication_review
    ? [
        "## 本次有限用药规则核对",
        draft.medication_review.conclusion,
        "",
        ...draft.medication_review.findings.flatMap((finding) => [
          `- **【${finding.severity}】${finding.title}**：${finding.conclusion}`,
          `  - 复核建议：${finding.clinician_action}`,
        ]),
        "",
        "### 规则来源",
        ...draft.medication_review.sources.map(
          (source) => `- ${source.title}（${source.locator}；${source.content_sha256}）`
        ),
        "",
        `> ${draft.medication_review.disclaimer}`,
        "",
      ]
    : [];

  return [
    "# 五大处方待临床复核草案",
    "",
    "> 状态：待临床复核，不可自行执行。不是正式处方或诊断。",
    "",
    "## 患者资料摘要（待核对）",
    `- 年龄：${draft.patient_summary.age === null ? "未提供" : `${draft.patient_summary.age} 岁`}`,
    `- 性别：${({ female: "女", male: "男", other: "其他", unknown: "未提供" } as const)[draft.patient_summary.sex]}`,
    "- 健康目标：",
    ...draft.patient_summary.health_goals.map((item) => `  - ${item}`),
    "- 当前关注：",
    ...draft.patient_summary.current_concerns.map((item) => `  - ${item}`),
    "",
    "## 健康评估摘要",
    draft.health_assessment.summary,
    "",
    "### 需重点复核",
    ...draft.health_assessment.key_issues.map((item) => `- ${item}`),
    "",
    "### 风险因素",
    ...bullets(draft.health_assessment.risk_factors, "未列出额外风险因素。"),
    "",
    ...medication,
    ...medicationReview,
    ...exercise,
    ...nutrition,
    ...psychological,
    ...rehabilitation,
    "## 证据来源",
    ...draft.evidence_sources.map(
      (source) =>
        `- **${source.evidence_id}** · ${source.source}：${source.title}（${source.locator}）${source.url ? ` [查看来源](${source.url})` : ""}`
    ),
    "",
    `上传资料：本次使用 ${draft.uploaded_document_ids.length} 份上传资料作为患者资料证据；它们不等同于本地医学知识库来源。`,
    "",
    `上传图片：本次使用 ${draft.uploaded_image_evidence_ids.length} 张病例图片作为患者资料证据。`,
    "",
    `> ${draft.disclaimer}`,
  ].join("\n");
}
