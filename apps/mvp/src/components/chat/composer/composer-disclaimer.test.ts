import assert from "node:assert/strict";
import test from "node:test";

import { MEDICAL_DISCLAIMER } from "../../../lib/constants.ts";
import { shouldShowComposerDisclaimer } from "./composer-disclaimer.ts";

test("输入区提醒只在当前对话尚无输出级免责声明时显示", () => {
  assert.equal(shouldShowComposerDisclaimer([], MEDICAL_DISCLAIMER), true);
  assert.equal(
    shouldShowComposerDisclaimer([
      {
        role: "assistant",
        status: "done",
        hasDisclaimer: true,
        blocks: [
          {
            kind: "text",
            id: "answer",
            content: `三条建议。\n\n${MEDICAL_DISCLAIMER}`,
          },
        ],
      },
    ], MEDICAL_DISCLAIMER),
    false,
  );
});

test("用户消息和未完成正文不会提前移除页面底部提醒", () => {
  assert.equal(
    shouldShowComposerDisclaimer([
      {
        role: "user",
        status: "done",
        blocks: [{ kind: "text", id: "question", content: "如何预防跌倒？" }],
      },
      {
        role: "assistant",
        status: "streaming",
        hasDisclaimer: false,
        blocks: [{ kind: "text", id: "partial", content: "正在整理建议" }],
      },
    ], MEDICAL_DISCLAIMER),
    true,
  );
});

test("非医疗回答完成后不继续展示无关的医疗提醒", () => {
  assert.equal(
    shouldShowComposerDisclaimer(
      [
        {
          role: "assistant",
          status: "done",
          hasDisclaimer: false,
          blocks: [
            {
              kind: "text",
              id: "calculation",
              content: "18 乘以 7 的结果是 126。",
            },
          ],
        },
      ],
      MEDICAL_DISCLAIMER,
    ),
    false,
  );
});
