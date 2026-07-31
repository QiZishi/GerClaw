import { expect, test, type Page } from "@playwright/test";

async function enterGuestWorkspace(page: Page) {
  await page.goto("/");
  await page
    .getByRole("button", { name: "暂不登录，进入患者服务" })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "您好，我是 GerClaw 健康助手，有什么可以帮您？",
    }),
  ).toBeVisible();
}

test("guest completes and exports a real PHQ-9 assessment", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);

  await page.getByRole("button", { name: "健康综合评估" }).click();
  await expect(
    page.getByRole("heading", { name: "老年综合评估" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "开始 PHQ-9 筛查" })
    .click();

  for (let position = 1; position <= 9; position += 1) {
    await expect(page.getByText(`第 ${position} / 9 题`)).toBeVisible();
    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        /\/api\/gerclaw\/cga\/assessments\/[^/]+\/answers$/.test(
          response.url(),
        ),
    );
    await page.getByRole("button", { name: "完全不会", exact: true }).click();
    expect((await saved).status()).toBe(200);
  }

  await expect(
    page.getByText("所有题目都已保存，可以查看筛查结果。"),
  ).toBeVisible();
  const completed = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/gerclaw\/cga\/assessments\/[^/]+\/complete$/.test(
        response.url(),
      ),
  );
  await page.getByRole("button", { name: "查看筛查结果" }).click();
  expect((await completed).status()).toBe(200);
  await expect(
    page.getByRole("heading", { name: "筛查结果" }),
  ).toBeVisible();
  await expect(page.getByText(/得分：\s*0 \/ 27/)).toBeVisible();

  await page.getByRole("button", { name: "导出报告" }).click();
  const download = page.waitForEvent("download");
  await page
    .getByRole("menuitem", { name: "Markdown（便于保存）" })
    .click();
  const artifact = await download;
  expect(artifact.suggestedFilename()).toMatch(/\.md$/);
});

test("guest uploads a document and receives a source-bound model answer", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);

  const documentInput = page.locator('input[type="file"][accept*=".pdf"]');
  await documentInput.setInputFiles(
    "e2e/fixtures/synthetic-home-record.md",
  );
  await expect(page.getByText("资料已解析，发送即可。")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("synthetic-home-record.md")).toBeVisible();

  const assistantBubbles = page.locator(
    '[data-message-bubble][data-message-role="assistant"]',
  );
  const before = await assistantBubbles.count();
  const input = page.getByRole("textbox");
  await input.fill(
    "只根据我上传的居家记录回答：最高的收缩压是多少，记录中的药名是什么？不要补充其他建议。",
  );
  const response = page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "POST" &&
      candidate.url().endsWith("/api/gerclaw/chat"),
  );
  await page.getByRole("button", { name: "发送" }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0, {
    timeout: 120_000,
  });
  await expect(assistantBubbles).toHaveCount(before + 1, {
    timeout: 120_000,
  });
  const answer = await assistantBubbles.last().innerText();
  expect(answer).toContain("146");
  expect(answer).toContain("氨氯地平");
  expect(answer).not.toMatch(
    /内部错误|正在修复|trace[_\s-]?id|provider|checkpoint|schema|policy/i,
  );
  await page.screenshot({
    path: "output/playwright/stage7-real-use/document-upload.png",
    fullPage: true,
  });
});

test("guest creates a source-bound five-prescription draft", async ({
  page,
}) => {
  test.setTimeout(360_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);

  await page.getByRole("button", { name: "五大处方计划" }).click();
  const input = page.getByRole("textbox", {
    name: "输入文字、上传资料或使用语音…",
  });
  await expect(input).toBeVisible();
  await expect(
    page.getByText(
      "您好，我会结合您提供的资料整理五大处方。请先说说最想改善什么。",
    ),
  ).toBeVisible();
  const generated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/gerclaw\/clinical-intakes\/[^/]+\/prescription-draft$/.test(
        response.url(),
    ),
    { timeout: 300_000 },
  );
  const turns = [
    "我70岁，最想改善起身头晕并安全增加活动。近两周起身时偶尔头晕，无胸痛、无呼吸困难。已知高血压；正在服用氨氯地平5mg每日一次；无已知药物过敏。家庭血压约135/80mmHg，饮食普通，每天步行约20分钟，睡眠约7小时。",
    "补充：身高165厘米、体重65公斤，近期体重稳定；无跌倒，能独立行走和完成日常活动；不吸烟，偶尔饮酒；希望获得药物、运动、营养、心理和康复五方面的待医生复核建议。",
    "没有其他用药或补充剂，也没有肝肾功能异常的已知记录；请基于已提供资料生成待临床复核草案。",
  ];
  for (const turn of turns) {
    if (!(await input.isVisible().catch(() => false))) break;
    const turnSaved = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        /\/api\/gerclaw\/clinical-intakes\/[^/]+\/conversation-turn$/.test(
          response.url(),
        ),
    );
    await input.fill(turn);
    await page.getByRole("button", { name: "发送" }).click();
    expect((await turnSaved).status()).toBe(200);
  }

  expect((await generated).status()).toBe(200);
  await expect(
    page.getByText("五大处方草案已生成，可以查看草案内容。"),
  ).toBeVisible({ timeout: 120_000 });
  const reportPanel = page.getByLabel("五大处方报告");
  await expect(reportPanel).toBeVisible();
  await expect(reportPanel).toContainText("证据");
  await expect(
    page.getByText(/内部错误|正在修复|trace[_\s-]?id|provider|checkpoint/i),
  ).toHaveCount(0);
});

test("answer feedback, regeneration, export and artifact editing are durable", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);

  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  await input.fill("请计算 25×4，只用一句中文回答。");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0, {
    timeout: 90_000,
  });
  const assistant = page
    .locator('[data-message-bubble][data-message-role="assistant"]')
    .last();
  await expect(assistant).toContainText("100");

  const feedbackSaved = page.waitForResponse(
    (response) =>
      /\/api\/gerclaw\/runs\/[^/]+\/feedback$/.test(response.url()) &&
      response.request().method() === "PUT",
  );
  await assistant.getByRole("button", { name: "有帮助" }).click();
  expect((await feedbackSaved).status()).toBe(200);
  await expect(
    assistant.getByRole("button", { name: "撤销有帮助反馈" }),
  ).toBeVisible();

  await assistant.getByRole("button", { name: "重新生成" }).click();
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0, {
    timeout: 90_000,
  });
  await expect(assistant).toContainText("100");
  await expect(
    assistant.getByRole("group", { name: "回答版本" }),
  ).toBeVisible();

  await assistant.getByRole("button", { name: "分享" }).click();
  await expect(
    page.getByRole("heading", { name: "导出对话" }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.md$/);

  await assistant.getByRole("button", { name: "更多" }).click();
  await page.getByRole("menuitem", { name: "转为文档编辑" }).click();
  await expect(page.getByText("文档标题")).toBeVisible();
  const artifactPanel = page.getByLabel("文档产物");
  await expect(artifactPanel.getByRole("status")).toContainText("已保存", {
    timeout: 30_000,
  });
  const editor = page.getByPlaceholder("开始输入 Markdown...");
  await editor.fill("# 计算结果\n\n25 乘以 4 等于 100。");
  await expect(artifactPanel.getByRole("status")).toContainText("已保存", {
    timeout: 30_000,
  });
});
