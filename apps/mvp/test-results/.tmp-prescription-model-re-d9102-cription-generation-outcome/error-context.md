# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: .tmp-prescription-model.spec.ts >> record current real prescription generation outcome
- Location: .tmp-prescription-model.spec.ts:3:5

# Error details

```
Error: locator.click: Target page, context or browser has been closed
Call log:
  - waiting for getByText('五大处方信息收集', { exact: true })

```

# Test source

```ts
  1  | import { expect, test } from "playwright/test";
  2  | 
  3  | test("record current real prescription generation outcome", async ({ page }) => {
  4  |   test.setTimeout(240_000);
  5  |   await page.setViewportSize({ width: 1440, height: 900 });
  6  |   await page.goto("http://127.0.0.1:3052", { waitUntil: "domcontentloaded" });
  7  |   await page.getByText("我是医生", { exact: true }).click();
> 8  |   await page.getByText("五大处方信息收集", { exact: true }).click();
     |                                                     ^ Error: locator.click: Target page, context or browser has been closed
  9  |   await expect(page.getByRole("heading", { name: "五大处方信息收集" })).toBeVisible();
  10 |   const fields = page.locator("textarea");
  11 |   await fields.nth(0).fill("希望改善步行耐力和日常活动能力");
  12 |   await fields.nth(1).fill("近两周活动后容易疲劳，想了解安全运动和营养建议");
  13 |   await page.getByRole("button", { name: "保存信息" }).click();
  14 |   await expect(page.getByRole("button", { name: "生成待审核草案" })).toBeEnabled();
  15 |   await page.getByRole("button", { name: "生成待审核草案" }).click();
  16 |   const success = page.getByRole("heading", { name: "五大处方草案" });
  17 |   const failure = page.getByText(
  18 |     /本地医学证据暂未就绪|生成服务暂时不可用|检测到可能需要紧急就医/
  19 |   );
  20 |   await expect(success.or(failure)).toBeVisible({ timeout: 210_000 });
  21 |   await page.screenshot({ path: "/tmp/gerclaw-audit/prescription-current-outcome.png", fullPage: true });
  22 | });
  23 | 
```