import { expect, test, type Page } from "@playwright/test";
import { fivePrescriptionDraftFixture } from "./fixtures/five-prescription-draft";

const intakeId = "11111111-1111-4111-8111-111111111111";
const sessionId = "22222222-2222-4222-8222-222222222222";

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
      await respond(fivePrescriptionDraftFixture);
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

  const reportHeading = page.getByRole("heading", { name: "五大处方待临床复核草案" });
  await expect(reportHeading).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();
  await expect(reportHeading).toHaveCount(0);
  const reopen = page.getByRole("button", { name: "查看五大处方草案" });
  await expect(reopen).toBeVisible();
  await reopen.click();
  await expect(reportHeading).toBeVisible();
});

test("a restored prescription draft can be reopened after closing the desktop panel", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);

  await page.route("**/api/gerclaw/clinical-intakes**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const respond = (body: unknown) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
    if (request.method() === "POST" && path.endsWith("/clinical-intakes")) {
      await respond(intake(5, true));
      return;
    }
    if (request.method() === "GET" && path.endsWith(`/clinical-intakes/${intakeId}/prescription-drafts`)) {
      await respond({
        items: [{
          draft_id: "33333333-3333-4333-8333-333333333333",
          intake_id: intakeId,
          created_at: "2026-08-11T08:00:00.000Z",
          draft: fivePrescriptionDraftFixture,
          reviews: [],
        }],
      });
      return;
    }
    await route.fallback();
  });

  await page.getByRole("button", { name: "五大处方计划" }).click();
  const report = page.getByLabel("五大处方报告");
  await expect(report).toBeVisible();
  await report.getByRole("button", { name: "关闭" }).click();
  await expect(report).toHaveCount(0);
  await page.getByRole("button", { name: "查看五大处方草案" }).click();
  await expect(page.getByLabel("五大处方报告")).toBeVisible();
  await expect(page.getByText("已恢复最近一次五大处方草案，您可以在右侧查看。")).toBeVisible();
});
