import assert from "node:assert/strict";
import test from "node:test";

import { clampSidebarWidth, sidebarWidthFromKey } from "./workbench-layout.ts";

test("sidebar width clamps persisted and pointer values", () => {
  assert.equal(clampSidebarWidth(100), 220);
  assert.equal(clampSidebarWidth(318.6), 319);
  assert.equal(clampSidebarWidth(999), 420);
  assert.equal(clampSidebarWidth(Number.NaN), 272);
});

test("sidebar keyboard resizing supports bounds and accelerated steps", () => {
  assert.equal(sidebarWidthFromKey(272, "ArrowLeft"), 256);
  assert.equal(sidebarWidthFromKey(272, "ArrowRight", true), 320);
  assert.equal(sidebarWidthFromKey(272, "Home"), 220);
  assert.equal(sidebarWidthFromKey(272, "End"), 420);
  assert.equal(sidebarWidthFromKey(272, "Enter"), null);
});
