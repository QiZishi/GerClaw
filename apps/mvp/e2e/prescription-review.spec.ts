import { expect, test } from "@playwright/test";
import { fivePrescriptionDraftFixture } from "./fixtures/five-prescription-draft";

const doctorActorId = "usr_account_11111111111111111111111111111111";
const patientActorId = "usr_account_22222222222222222222222222222222";
const draftId = "33333333-3333-4333-8333-333333333333";
const intakeId = "44444444-4444-4444-8444-444444444444";

test("doctor sees immutable model draft and separately versioned amendments", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.route("**/api/account/status", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      authenticated: true,
      actor_id: doctorActorId,
      role: "doctor",
      account_role: "doctor",
    }),
  }));

  const reviews: Array<Record<string, unknown>> = [];
  await page.route("**/api/gerclaw/access-grants/patients/**/prescription-drafts**", async (route) => {
    const request = route.request();
    if (request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{
            draft_id: draftId,
            intake_id: intakeId,
            created_at: "2026-08-11T08:00:00.000Z",
            draft: fivePrescriptionDraftFixture,
            reviews,
          }],
        }),
      });
      return;
    }
    if (request.method() === "POST") {
      const body = request.postDataJSON() as {
        decision: "approved" | "returned";
        review_note: string;
        amended_markdown: string | null;
        amendment_evidence_ids: string[];
      };
      const review = {
        review_id: `${reviews.length + 1}`.padStart(8, "0") + "-5555-4555-8555-555555555555",
        draft_id: draftId,
        doctor_actor_id: doctorActorId,
        decision: body.decision,
        review_note: body.review_note,
        amended_markdown: body.amended_markdown,
        amendment_evidence_ids: body.amendment_evidence_ids,
        revision: reviews.length + 1,
        reviewed_at: `2026-08-11T${String(reviews.length + 9).padStart(2, "0")}:00:00.000Z`,
      };
      reviews.unshift(review);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(review) });
      return;
    }
    await route.fallback();
  });

  await page.goto("/");
  await expect(page.getByText("医生工作台", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "用户菜单" }).click();
  await page.getByRole("menuitem", { name: "五大处方草案复核" }).click();
  await expect(page.getByRole("heading", { name: "五大处方草案复核" })).toBeVisible();
  await page.getByLabel("患者代码").fill(patientActorId);
  await page.getByRole("button", { name: "查看草案" }).click();

  const record = page.getByRole("article");
  await expect(record.getByText("待复核", { exact: true })).toBeVisible();
  await expect(record.getByRole("heading", { name: "模型初稿（只读，不可覆盖）" })).toBeVisible();
  await expect(record.getByRole("heading", { name: "医生修订版" })).toBeVisible();
  await expect(record.getByText("尚无医生修订版；模型初稿仍保持不变。")).toBeVisible();

  await record.getByRole("button", { name: "编辑医生修订版" }).click();
  await record.getByPlaceholder("开始输入 Markdown...").fill("# 医生修订版\n\n建议先由医生核对跌倒风险。");
  await expect(record.getByRole("checkbox")).toBeChecked();
  await record.getByLabel("复核意见").fill("已核对证据与风险边界。");
  await record.getByRole("button", { name: "审核通过" }).click();
  await expect(record.getByText("已通过", { exact: true })).toBeVisible();
  await expect(record.getByText("建议先由医生核对跌倒风险。")).toBeVisible();
  await expect(record.getByRole("heading", { name: "模型初稿（只读，不可覆盖）" })).toBeVisible();

  await record.getByLabel("复核意见").fill("请患者补充近期跌倒发生时间。");
  await record.getByRole("button", { name: "退回补充" }).click();
  await expect(record.getByText("已退回", { exact: true })).toBeVisible();
  await expect(record.getByText("建议先由医生核对跌倒风险。")).toBeVisible();
  expect(reviews).toHaveLength(2);
});

test("patient workspace does not expose clinician review controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/account/status", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      authenticated: true,
      actor_id: patientActorId,
      role: "patient",
      account_role: "patient",
    }),
  }));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "您好，我是 GerClaw 健康助手，有什么可以帮您？" })).toBeVisible();
  await page.getByRole("button", { name: "打开菜单" }).click();
  await page.getByRole("button", { name: "用户菜单" }).click();
  await expect(page.getByRole("menuitem", { name: "五大处方草案复核" })).toHaveCount(0);
});
