import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const runRealUseAudit = process.env.GERCLAW_RUN_REAL_USE_AUDIT === "1";
const realUseTest = runRealUseAudit ? test : test.skip;
const INTERNAL_DETAIL =
  /CHAT_[A-Z_]+|EVOLUTION_[A-Z_]+|checkpoint|schema|policy|tool_call|<invoke|<parameter|<tool_call|内部错误|正在修复|校验失败|安全边界|模型供应商/i;
const PUBLIC_FAILURE =
  /这次回答没有完整生成|本次回复未完整生成|本次执行未完成|暂时无法完成|服务暂时不可用|请稍后重试/;
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
  const markdownBody = assistantBubbles.last().locator(".markdown-body");
  expect(visible.trim().length).toBeGreaterThan(20);
  if ((await markdownBody.count()) > 0) {
    expect(await markdownBody.innerText()).not.toMatch(/\[C[1-9]\d{0,2}\]/);
  }
  expect(visible).not.toMatch(INTERNAL_DETAIL);
  expect(visible).not.toMatch(PUBLIC_FAILURE);
  expect(visible.split(DISCLAIMER).length - 1).toBeLessThanOrEqual(1);
  await expect(assistantBubbles.last().getByText("执行详情", { exact: true })).toBeVisible();
  return visible;
}

realUseTest(
  "real model tasks stay useful with public execution details and no private internals",
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

    const asrAudio = readFileSync(
      "public/audio/cga/phq9/2026-07-16/questions/phq9_1.wav",
    ).toString("base64");
    const asrProbe = await page.evaluate(async (audio) => {
      const response = await fetch("/api/gerclaw/voice/asr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audio, format: "wav" }),
      });
      return {
        status: response.status,
        body: await response.text(),
      };
    }, asrAudio);
    expect([200, 502, 503]).toContain(asrProbe.status);
    if (asrProbe.status === 200) {
      const payload = JSON.parse(asrProbe.body) as {
        schema_version?: string;
        text?: string;
      };
      expect(payload.schema_version).toBe("voice-asr-response-v1");
      expect(payload.text?.trim().length ?? 0).toBeGreaterThan(0);
    } else {
      expect(asrProbe.body).toMatch(
        /VOICE_ASR_(?:UNAVAILABLE|INVALID_RESPONSE)|VOICE_UNAVAILABLE/,
      );
    }
    test.info().annotations.push({
      type: "asr-status",
      description:
        asrProbe.status === 200
          ? "real provider transcription succeeded"
          : `real provider degraded with HTTP ${asrProbe.status}`,
    });

    const calculation = await sendAndRead(
      page,
      "请计算 18×7，并用一句自然中文说明结果。不要扩展到健康建议。",
    );
    expect(calculation).toContain("126");
    expect(calculation).not.toContain(DISCLAIMER);
    const calculationBubble = page
      .locator('[data-message-bubble][data-message-role="assistant"]')
      .last();
    await calculationBubble.getByText("执行详情", { exact: true }).click();
    await expect(calculationBubble.getByText("模型服务", { exact: true })).toBeVisible();
    await expect(calculationBubble.getByText("Trace", { exact: true })).toBeVisible();
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
    const consultationBubble = page
      .locator('[data-message-bubble][data-message-role="assistant"]')
      .last();
    await expect(
      consultationBubble.getByText(/医学检索/).first(),
    ).toBeVisible();

    const familyChecklist = await sendAndRead(
      page,
      "请基于刚才的情况，改成给家属看的三点清单，并保留什么时候需要及时就医。",
    );
    expect(familyChecklist).toMatch(/家属|清单|就医/);
    expect(familyChecklist).not.toMatch(
      /紧急就医警示|非典型的心血管危险征兆|以上建议仅供辅助|不能替代医生|高龄患者/,
    );
    expect(familyChecklist).not.toMatch(/(?:^|\s)\*\s+\S/);
    await expect(
      page
        .locator('[data-message-bubble][data-message-role="assistant"]')
        .last()
        .locator("ol > li"),
    ).toHaveCount(3);
    expect(familyChecklist).not.toMatch(
      /超过半数|唯一预警|致命|代偿机制正在失效|高龄群体|心肌梗死/,
    );
    expect(familyChecklist.length).toBeLessThan(1_200);
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
            (ttsUnavailableResponses > 0 || asrProbe.status === 503) &&
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
