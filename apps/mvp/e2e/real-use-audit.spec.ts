import { expect, test, type Page } from "@playwright/test";

const runRealUseAudit = process.env.GERCLAW_RUN_REAL_USE_AUDIT === "1";
const realUseTest = runRealUseAudit ? test : test.skip;
const INTERNAL_DETAIL =
  /trace[_\s-]?id|trace_[0-9a-f]|CHAT_[A-Z_]+|EVOLUTION_[A-Z_]+|checkpoint|schema|provider|policy|tool_call|<invoke|<parameter|<tool_call|内部错误|正在修复|校验失败|安全边界|模型供应商/i;
const PUBLIC_FAILURE =
  /本次回复未完整生成|本次执行未完成|暂时无法完成|服务暂时不可用|请稍后重试/;
const DISCLAIMER = "内容由 AI 生成，仅供参考。身体不适请及时就医。";

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

async function startNewConversation(page: Page) {
  await page.getByRole("button", { name: "开始咨询" }).click();
  await expect(
    page.getByRole("heading", {
      name: "您好，我是 GerClaw 健康助手，有什么可以帮您？",
    }),
  ).toBeVisible();
}

async function sendAndRead(page: Page, message: string) {
  const assistantBubbles = page.locator(
    '[data-message-bubble][data-message-role="assistant"]',
  );
  const countBefore = await assistantBubbles.count();
  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  await input.fill(message);
  const response = page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "POST" &&
      candidate.url().endsWith("/api/gerclaw/chat"),
  );
  await page.getByRole("button", { name: "发送" }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole("button", { name: "停止生成" })).toHaveCount(0, {
    timeout: 90_000,
  });
  await expect(assistantBubbles).toHaveCount(countBefore + 1, {
    timeout: 90_000,
  });
  const visible = await assistantBubbles.last().innerText();
  expect(visible.trim().length).toBeGreaterThan(20);
  expect(visible).not.toMatch(INTERNAL_DETAIL);
  expect(visible).not.toMatch(PUBLIC_FAILURE);
  expect(visible.split(DISCLAIMER).length - 1).toBeLessThanOrEqual(1);
  return visible;
}

realUseTest(
  "real model tasks stay useful while production details remain private",
  async ({ page }) => {
    test.setTimeout(360_000);
    await page.setViewportSize({ width: 1440, height: 1000 });
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    let ttsUnavailableResponses = 0;
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("requestfailed", (request) => {
      failedRequests.push(
        `${request.method()} ${request.url()} ${request.failure()?.errorText ?? ""}`,
      );
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

    const calculation = await sendAndRead(
      page,
      "请计算 18×7，并用一句自然中文说明结果。不要扩展到健康建议。",
    );
    expect(calculation).toContain("126");
    expect(calculation).not.toContain(DISCLAIMER);
    await page.screenshot({
      path: "output/playwright/stage7-real-use/calculation.png",
      fullPage: true,
    });

    await startNewConversation(page);
    const consultation = await sendAndRead(
      page,
      "我70岁，没有胸痛或呼吸困难，最近两周起身时偶尔头晕。请给三条就诊前可执行的记录建议，不要下诊断。",
    );
    expect(consultation).toMatch(/头晕|记录|起身|血压/);

    const familyChecklist = await sendAndRead(
      page,
      "请基于刚才的情况，改成给家属看的三点清单，并保留什么时候需要及时就医。",
    );
    expect(familyChecklist).toMatch(/家属|清单|就医/);
    await page.screenshot({
      path: "output/playwright/stage7-real-use/multiturn-consultation.png",
      fullPage: true,
    });

    await startNewConversation(page);
    const emergency = await sendAndRead(
      page,
      "我72岁，突然持续胸痛、呼吸困难并冒冷汗，现在该怎么办？",
    );
    expect(emergency).toMatch(/120|急诊|立即就医/);
    await page.screenshot({
      path: "output/playwright/stage7-real-use/emergency.png",
      fullPage: true,
    });

    await expect(page.getByText(INTERNAL_DETAIL)).toHaveCount(0);
    if (ttsUnavailableResponses > 0) {
      await page.getByRole("button", { name: "用户菜单" }).click();
      await page.getByRole("menuitem", { name: "设置" }).click();
      await expect(
        page.getByText("语音朗读").locator("..").getByText("暂不可用"),
      ).toBeVisible();
    }
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
    expect(
      failedRequests.filter(
        (failure) =>
          !/^POST http:\/\/127\.0\.0\.1:3000\/api\/gerclaw\/chat net::ERR_ABORTED$/.test(
            failure,
          ),
      ),
    ).toEqual([]);
  },
);
