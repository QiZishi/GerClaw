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
});
