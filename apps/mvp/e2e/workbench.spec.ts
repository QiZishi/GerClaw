import AxeBuilder from "@axe-core/playwright";
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

async function expectNoPageOverflow(page: Page, viewportWidth: number) {
  const metrics = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(metrics.documentWidth).toBeLessThanOrEqual(viewportWidth);
  expect(metrics.bodyWidth).toBeLessThanOrEqual(viewportWidth);
}

async function expectSeniorTargets(page: Page) {
  const undersized = await page.evaluate(() =>
    Array.from(
      document.querySelectorAll<HTMLElement>(
        'button,a[href],input,textarea,select,[role="button"]',
      ),
    )
      .filter((element) => element.getAttribute("role") !== "separator")
      .filter((element) => {
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          box.width > 0 &&
          box.height > 0 &&
          style.visibility !== "hidden" &&
          (box.width < 48 || box.height < 48)
        );
      })
      .map((element) => {
        const box = element.getBoundingClientRect();
        return {
          name:
            element.getAttribute("aria-label") ??
            element.textContent?.trim().slice(0, 40),
          width: Math.round(box.width),
          height: Math.round(box.height),
        };
      }),
  );
  expect(undersized).toEqual([]);
}

async function expectNoBlockingAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations
    .filter(
      (violation) =>
        violation.impact === "serious" || violation.impact === "critical",
    )
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.map((node) => ({
        target: node.target,
        summary: node.failureSummary,
      })),
    }));
  expect(blocking).toEqual([]);
}

test("desktop workbench keeps keyboard layout and composer semantics", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);
  await expect(page.locator("html")).toHaveClass(/senior-mode/);
  await expectNoPageOverflow(page, 1440);

  const sidebar = page.getByRole("complementary");
  const separator = page.getByRole("separator", {
    name: "调整会话栏宽度",
  });
  const initialWidth = (await sidebar.boundingBox())?.width ?? 0;
  await separator.press("ArrowRight");
  expect((await sidebar.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(
    initialWidth + 15,
  );
  await separator.dblclick();
  expect((await sidebar.boundingBox())?.width).toBeCloseTo(272, 0);

  await page.getByRole("button", { name: "折叠侧边栏" }).click();
  const collapsed = page.getByRole("navigation", {
    name: "折叠的会话导航",
  });
  await expect(collapsed).toBeVisible();
  expect((await collapsed.boundingBox())?.width).toBeCloseTo(56, 0);
  await page.getByRole("button", { name: "展开" }).click();

  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  let chatRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/gerclaw/chat")) chatRequests += 1;
  });
  await input.fill("组合输入测试");
  await input.dispatchEvent("keydown", {
    key: "Enter",
    code: "Enter",
    isComposing: true,
  });
  await expect(input).toHaveValue("组合输入测试");
  expect(chatRequests).toBe(0);
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("组合输入测试\n");
  expect(chatRequests).toBe(0);

  await expectSeniorTargets(page);
  await expectNoBlockingAxeViolations(page);
});

test("mobile workbench uses an accessible session drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enterGuestWorkspace(page);
  await expectNoPageOverflow(page, 390);
  await expectSeniorTargets(page);
  await expectNoBlockingAxeViolations(page);

  await page.getByRole("button", { name: "打开菜单" }).click();
  const drawer = page.getByRole("dialog", { name: "会话菜单" });
  await expect(drawer).toBeVisible();
  await expectSeniorTargets(page);
  await expectNoBlockingAxeViolations(page);

  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expectNoPageOverflow(page, 390);

  await page.getByRole("button", { name: "查看我的健康记录" }).click();
  const profilePanel = page.getByRole("dialog", { name: "健康画像" });
  await expect(profilePanel).toBeVisible();
  await expectSeniorTargets(page);
  await expectNoBlockingAxeViolations(page);
  await page.keyboard.press("Escape");
  await expect(profilePanel).toBeHidden();
});

test("raw provider protocol markup never reaches the visible answer", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const consoleErrors: string[] = [];
  let ttsUnavailableResponses = 0;
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (
      response.status() === 503 &&
      response.url().endsWith("/api/gerclaw/voice/tts")
    ) {
      ttsUnavailableResponses += 1;
    }
  });
  await enterGuestWorkspace(page);
  const assistantBubbles = page.locator(
    '[data-message-bubble][data-message-role="assistant"]',
  );
  const assistantCountBefore = await assistantBubbles.count();
  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  await input.fill("请只给三个最重要、最容易执行的规律作息建议。");
  const response = page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "POST" &&
      candidate.url().endsWith("/api/gerclaw/chat"),
  );
  await page.getByRole("button", { name: "发送" }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0, {
    timeout: 75_000,
  });
  await expect(
    page.getByText(
      /<invoke|<parameter|<tool_call|未通过最终安全校验|正在修复|内部错误/,
    ),
  ).toHaveCount(0);
  await expect(assistantBubbles).toHaveCount(assistantCountBefore + 1);
  const answer = await assistantBubbles.last().innerText();
  expect(answer.trim().length).toBeGreaterThan(20);
  expect(answer).not.toMatch(
    /CHAT_[A-Z_]+|checkpoint|schema|内部错误|正在修复/i,
  );
  await expect(
    assistantBubbles.last().getByText("执行详情", { exact: true }),
  ).toBeVisible();
  const helpful = page.getByRole("button", { name: "有帮助" });
  await expect(helpful).toBeVisible();
  await expectNoBlockingAxeViolations(page);
  await page.screenshot({
    path: "output/playwright/stage6-output-repair/desktop.png",
    fullPage: true,
  });
  expect(ttsUnavailableResponses).toBeLessThanOrEqual(1);
  expect(
    consoleErrors.filter(
      (message) =>
        !(
          ttsUnavailableResponses > 0 &&
          /Failed to load resource:.*503/.test(message)
        ),
    ),
  ).toEqual([]);
});

test("a Run in another conversation does not take over the current Composer", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);

  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  await input.fill("请用一句话介绍保持规律作息的好处");

  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止生成" })).toBeVisible();

  await page.getByRole("button", { name: "开始咨询" }).click();
  await expect(
    page.getByRole("heading", {
      name: "您好，我是 GerClaw 健康助手，有什么可以帮您？",
    }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "语音输入" })).toBeEnabled();

  await page.getByRole("button", { name: "用户菜单" }).click();
  await page.getByRole("menuitem", { name: "对话记录" }).click();
  await page
    .getByRole("button", { name: /请用一句话介绍保持规律作息的好处/ })
    .click();
  const stop = page.getByRole("button", { name: "停止生成" });
  if (await stop.isVisible()) {
    await stop.click();
    await expect(stop).toHaveCount(0, { timeout: 15_000 });
  }
});

test("a running Run accepts queued and immediate user directives", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(
      `${request.method()} ${request.url()} ${request.failure()?.errorText ?? ""}`,
    );
  });
  await enterGuestWorkspace(page);

  const initialInstruction =
    "请分步骤说明老年人如何建立规律作息，并给出一周可执行计划。";
  const queuedInstruction = "下一步请补充家属可以怎样协助。";
  const steeringInstruction = "先改为只给三个最重要、最容易执行的建议。";
  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  await input.fill(initialInstruction);
  const initialResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/gerclaw/chat"),
  );
  await page.getByRole("button", { name: "发送" }).click();
  expect((await initialResponse).status()).toBe(200);

  const runningInput = page.getByRole("textbox", {
    name: "输入新要求，可选择立即调整或排队继续…",
  });
  await expect(runningInput).toBeVisible();
  await runningInput.fill(queuedInstruction);
  const queueResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/gerclaw\/chat\/[^/]+\/directives\/queue$/.test(response.url()),
  );
  await page.getByRole("button", { name: "排队继续" }).click();
  expect((await queueResponse).status()).toBe(201);
  await expect(page.getByText(queuedInstruction, { exact: true })).toBeVisible();

  await runningInput.fill(steeringInstruction);
  const steerResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/gerclaw\/chat\/[^/]+\/directives\/steer$/.test(response.url()),
  );
  await page.getByRole("button", { name: "立即调整" }).click();
  expect((await steerResponse).status()).toBe(200);
  await expect(
    page.getByText(steeringInstruction, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      /未通过最终安全校验|正在修复|内部错误|<invoke|<parameter|<tool_call/,
    ),
  ).toHaveCount(0);
  await expectNoPageOverflow(page, 1440);
  await expectSeniorTargets(page);
  await expectNoBlockingAxeViolations(page);
  await page.screenshot({
    path: "output/playwright/stage6-directives/desktop-steer.png",
    fullPage: true,
  });

  const stop = page.getByRole("button", { name: "停止生成" });
  if (await stop.isVisible()) {
    await stop.click();
    await expect(stop).toHaveCount(0, { timeout: 15_000 });
  }
  expect(consoleErrors).toEqual([]);
  expect(
    failedRequests.filter(
      (failure) =>
        !/^POST http:\/\/127\.0\.0\.1:3000\/api\/gerclaw\/chat(?:\/trace_[^/]+\/directives\/steer)? net::ERR_ABORTED$/.test(failure),
    ),
  ).toEqual([]);
});

test("stop remains effective while an immediate adjustment is handing off", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enterGuestWorkspace(page);

  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  await input.fill("请详细制定一周规律作息计划，并分步骤解释。");
  const initialResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/gerclaw/chat"),
  );
  await page.getByRole("button", { name: "发送" }).click();
  expect((await initialResponse).status()).toBe(200);

  const runningInput = page.getByRole("textbox", {
    name: "输入新要求，可选择立即调整或排队继续…",
  });
  await runningInput.fill("改为只列三个最重要的建议。");
  const steerResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/gerclaw\/chat\/[^/]+\/directives\/steer$/.test(response.url()),
  );
  await page.getByRole("button", { name: "立即调整" }).click();
  await expect(page.getByRole("button", { name: "停止生成" })).toBeEnabled();
  await page.getByRole("button", { name: "停止生成" }).click();

  expect([200, 409]).toContain((await steerResponse).status());
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0, {
    timeout: 45_000,
  });
  await expect(page.getByRole("button", { name: "发送" })).toBeEnabled();
  await expect(
    page.getByText(/内部错误|正在修复|<invoke|<parameter|<tool_call/),
  ).toHaveCount(0);
  await expectNoBlockingAxeViolations(page);
});
