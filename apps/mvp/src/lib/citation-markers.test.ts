import assert from "node:assert/strict";
import test from "node:test";

import { findCitationMatches } from "./citation-markers.ts";

test("accepts only server-owned bounded citation markers", () => {
  assert.deepEqual(findCitationMatches("建议 [C1]，补充 [C12]。"), [
    { fullMatch: "[C1]", citeId: 1, index: 3 },
    { fullMatch: "[C12]", citeId: 12, index: 11 },
  ]);
  assert.deepEqual(findCitationMatches("模型标记 [E1] [W1] [1] [C0] [C1000]"), []);
});
