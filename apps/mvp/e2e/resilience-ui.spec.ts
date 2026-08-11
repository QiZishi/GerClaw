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

test("offline state is announced and clears after the network recovers", async ({
  context,
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enterGuestWorkspace(page);

  await expect(page.getByTestId("offline-banner")).toHaveCount(0);
  await context.setOffline(true);

  const banner = page.getByTestId("offline-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toHaveAttribute("role", "status");
  await expect(banner).toHaveText("网络已断开，请检查网络连接");
  const bannerBox = await banner.boundingBox();
  expect(bannerBox?.height ?? 0).toBeGreaterThanOrEqual(48);
  const bannerFontSize = await banner.evaluate((element) =>
    Number.parseFloat(window.getComputedStyle(element).fontSize),
  );
  expect(bannerFontSize).toBeGreaterThanOrEqual(18);
  await page.screenshot({
    path: "output/playwright/resilience/offline-banner-mobile.png",
    fullPage: true,
  });

  await context.setOffline(false);
  await expect(banner).toHaveCount(0);
  await expect(page.getByText("网络已恢复连接", { exact: true })).toBeVisible();
});

test("a failed chat turn exposes a real retry without duplicating the user message", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let chatRequests = 0;
  await page.route("**/api/gerclaw/chat", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    chatRequests += 1;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "MODEL_PROVIDER_UNAVAILABLE",
          message: "provider detail must not be shown",
        },
      }),
    });
  });

  await enterGuestWorkspace(page);
  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  await input.fill("这是用于验证失败重试的界面测试问题。 ");
  await page.getByRole("button", { name: "发送" }).click();

  const userMessages = page.locator(
    '[data-message-bubble][data-message-role="user"]',
  );
  await expect(userMessages).toHaveCount(1);
  await expect(page.getByRole("alert", { name: "回答未完成提醒" })).toContainText(
    "服务暂时不稳定，这次回答没有完整生成。请稍后重试",
  );
  await expect(page.getByText("provider detail must not be shown")).toHaveCount(0);

  const retry = page.getByRole("button", { name: "重试", exact: true });
  await expect(retry).toBeVisible();
  const retryBox = await retry.boundingBox();
  expect(retryBox?.height ?? 0).toBeGreaterThanOrEqual(48);
  await retry.click();

  await expect.poll(() => chatRequests).toBe(2);
  await expect(userMessages).toHaveCount(1);
  await expect(page.getByRole("alert", { name: "回答未完成提醒" })).toBeVisible();
  await page.screenshot({
    path: "output/playwright/resilience/chat-retry-mobile.png",
    fullPage: true,
  });
});
