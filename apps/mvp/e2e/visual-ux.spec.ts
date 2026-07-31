import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

const DISCLAIMER = "内容由 AI 生成，仅供参考。身体不适请及时就医。";
const INTERNAL_DETAIL =
  /trace[_\s-]?id|CHAT_[A-Z_]+|EVOLUTION_[A-Z_]+|checkpoint|schema|provider|tool_call|内部错误|正在修复|校验失败|安全边界|模型供应商/i;

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

async function expectInsideViewport(
  locator: Locator,
  width: number,
  height: number,
) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect(box?.y ?? -1).toBeGreaterThanOrEqual(0);
  expect((box?.x ?? 0) + (box?.width ?? width + 1)).toBeLessThanOrEqual(width);
  expect((box?.y ?? 0) + (box?.height ?? height + 1)).toBeLessThanOrEqual(
    height,
  );
}

async function expectNoPageOverflow(page: Page, viewportWidth: number) {
  const metrics = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(metrics.body).toBeLessThanOrEqual(viewportWidth);
  expect(metrics.document).toBeLessThanOrEqual(viewportWidth);
}

async function expectNoBlockingAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations
      .filter(
        (violation) =>
          violation.impact === "serious" || violation.impact === "critical",
      )
      .map((violation) => violation.id),
  ).toEqual([]);
}

test("mobile senior workspace keeps the composer and reminder readable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enterGuestWorkspace(page);

  const input = page.getByRole("textbox", {
    name: "请描述您想咨询的健康问题…",
  });
  const composer = input.locator(
    "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' border-t ')][1]",
  );
  const disclaimer = page.getByText(DISCLAIMER, { exact: true });
  const toolStrip = page.getByLabel("对话工具，可横向滚动");
  const imageButton = page.getByRole("button", { name: "上传图片" });
  const fileButton = page.getByRole("button", {
    name: "上传文件（PDF/DOCX/MD/图片）",
  });

  await expect(composer).toBeVisible();
  await expect(disclaimer).toBeVisible();
  await expectInsideViewport(composer, 390, 844);
  await expectInsideViewport(disclaimer, 390, 844);
  const stripBox = await toolStrip.boundingBox();
  const imageBox = await imageButton.boundingBox();
  const fileBox = await fileButton.boundingBox();
  expect(stripBox).not.toBeNull();
  expect(imageBox).not.toBeNull();
  expect(fileBox).not.toBeNull();
  expect(imageBox?.x ?? -1).toBeGreaterThanOrEqual(stripBox?.x ?? 0);
  expect((fileBox?.x ?? 0) + (fileBox?.width ?? 1)).toBeLessThanOrEqual(
    (stripBox?.x ?? 0) + (stripBox?.width ?? 0),
  );
  await expectNoPageOverflow(page, 390);
  await expect(page.getByText(INTERNAL_DETAIL)).toHaveCount(0);
  await expectNoBlockingAxeViolations(page);
  await page.screenshot({
    path: "output/playwright/stage7-ux/mobile-welcome.png",
  });

  await page.getByRole("button", { name: "打开菜单" }).click();
  const drawer = page.getByRole("dialog", { name: "会话菜单" });
  await expect(drawer).toBeVisible();
  await expect
    .poll(async () => (await drawer.boundingBox())?.x ?? -1)
    .toBeGreaterThanOrEqual(0);
  await expectInsideViewport(drawer, 390, 844);
  await page.screenshot({
    path: "output/playwright/stage7-ux/mobile-menu.png",
  });
});

test("tablet workspace keeps the health panel usable without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await enterGuestWorkspace(page);
  await page.getByRole("button", { name: "查看我的健康记录" }).click();

  const panel = page.getByRole("dialog", { name: "健康画像" });
  await expect(panel).toBeVisible();
  await expectInsideViewport(panel, 1024, 768);
  await expectNoPageOverflow(page, 1024);
  await expect(page.getByText(INTERNAL_DETAIL)).toHaveCount(0);
  await expectNoBlockingAxeViolations(page);
  await page.screenshot({
    path: "output/playwright/stage7-ux/tablet-health-profile.png",
  });
});
