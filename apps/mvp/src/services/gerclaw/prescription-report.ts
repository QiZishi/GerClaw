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
  ];
  const medication = [
    ...section(draft.medication.title, draft.medication),
    "### 用药核对与监测重点",
    ...(draft.medication.monitoring_requirements.length > 0
      ? draft.medication.monitoring_requirements.map((item) => `- ${item}`)
      : ["- 未提供额外监测事项；请由医生或药师核对。"]),
    "",
  ];
  const exercise = [
    ...section(draft.exercise.title, draft.exercise),
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
    "## 健康评估摘要",
    draft.health_assessment.summary,
    "",
    "### 需重点复核",
    ...draft.health_assessment.key_issues.map((item) => `- ${item}`),
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
    `> ${draft.disclaimer}`,
  ].join("\n");
}
