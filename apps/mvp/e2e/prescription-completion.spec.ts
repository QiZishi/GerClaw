import { expect, test, type Page } from "@playwright/test";

const intakeId = "11111111-1111-4111-8111-111111111111";
const sessionId = "22222222-2222-4222-8222-222222222222";

const evidence = [{
  evidence_id: "ev_local1234",
  title: "本地指南",
  source: "local",
  locator: "第 1 节",
  url: null,
}];
const recommendations = [{ content: "建议项目", evidence_ids: ["ev_local1234"] }];
const baseSection = {
  goal: "共同目标",
  recommendations,
  precautions: ["共同注意事项"],
  evidence_ids: ["ev_local1234"],
};
const draft = {
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
  uploaded_document_ids: [],
  uploaded_image_evidence_ids: [],
  disclaimer: "AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。",
};

function intake(turns: number, complete = false) {
  return {
    intake_id: intakeId,
    session_id: sessionId,
    kind: "prescription",
    definition_version: "prescription-v1",
    status: complete ? "information_complete_pending_governance" : "collecting",
    revision: turns + 1,
    conversation_turns: turns,
    title: "五大处方信息收集",
    description: "补齐关键信息后生成待临床复核草案",
    fields: [{ id: "health_goals", label: "健康目标", required: true, max_length: 500, placeholder: "请输入健康目标" }],
    answers: complete ? { health_goals: "安全增加活动" } : {},
    document_ids: [],
    image_evidence_ids: [],
    missing_required_fields: complete ? [] : ["health_goals"],
    governance_notice: "生成内容待临床复核，不可自行执行。",
    updated_at: "2026-08-11T08:00:00.000Z",
  };
}

async function enterGuestWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "暂不登录，进入患者服务" }).click();
  await expect(page.getByRole("heading", { name: "您好，我是 GerClaw 健康助手，有什么可以帮您？" })).toBeVisible();
}

test("the fifth incomplete turn switches to safe manual completion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enterGuestWorkspace(page);

  let conversationCalls = 0;
  let patchCalls = 0;
  let generationCalls = 0;
  await page.route("**/api/gerclaw/clinical-intakes**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

    if (request.method() === "POST" && path.endsWith("/clinical-intakes")) {
      await respond(intake(0));
      return;
    }
    if (request.method() === "GET" && path.endsWith(`/clinical-intakes/${intakeId}/prescription-drafts`)) {
      await respond({ items: [] });
      return;
    }
    if (request.method() === "POST" && path.endsWith(`/clinical-intakes/${intakeId}/conversation-turn`)) {
      conversationCalls += 1;
      await respond({
        intake: intake(conversationCalls),
        assistant_message: `请补充健康目标（第 ${conversationCalls} 个问题）。`,
        ready_to_generate: false,
      });
      return;
    }
    if (request.method() === "PATCH" && path.endsWith(`/clinical-intakes/${intakeId}`)) {
      patchCalls += 1;
      expect(request.postDataJSON()).toEqual({
        expected_revision: 6,
        answers: { health_goals: "安全增加活动" },
      });
      await respond(intake(5, true));
      return;
    }
    if (request.method() === "POST" && path.endsWith(`/clinical-intakes/${intakeId}/prescription-draft`)) {
      generationCalls += 1;
      await respond(draft);
      return;
    }
    await route.fallback();
  });

  await page.getByRole("button", { name: "五大处方计划" }).click();
  await expect(page.getByText(/信息补充：已完成 0\/5 轮/)).toBeVisible();
  await expect(page.getByText("正在准备对话…")).toHaveCount(0);
  const input = page.getByRole("textbox", { name: "输入文字、上传资料或使用语音…" });
  for (let turn = 1; turn <= 5; turn += 1) {
    const saved = page.waitForResponse((response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/gerclaw/clinical-intakes/${intakeId}/conversation-turn`),
    );
    await input.fill(`第 ${turn} 轮补充信息`);
    await page.getByRole("button", { name: "发送" }).click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByText(new RegExp(`信息补充：已完成 ${turn}/5 轮`))).toBeVisible();
  }

  await expect(page.getByText("请核对缺失信息")).toBeVisible();
  await expect(page.getByText(/信息补充：已完成 5\/5 轮/)).toBeVisible();
  await expect(input).toHaveCount(0);
  expect(conversationCalls).toBe(5);
  expect(generationCalls).toBe(0);

  await page.getByLabel("健康目标（必填）").fill("安全增加活动");
  await page.getByRole("button", { name: "保存并继续生成" }).click();
  await expect(page.getByText("五大处方草案已生成，可以查看草案内容。")).toBeVisible();
  expect(patchCalls).toBe(1);
  expect(generationCalls).toBe(1);
});
