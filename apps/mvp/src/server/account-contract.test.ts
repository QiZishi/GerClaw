import assert from "node:assert/strict";
import test from "node:test";

import { accountSessionSchema } from "./account-contract.ts";

const validSession = {
  access_token: "a".repeat(32),
  refresh_token: "r".repeat(32),
  token_type: "bearer",
  expires_in: 900,
  actor_id: "usr_account_0123456789abcdef0123456789abcdef",
  role: "patient",
  account_role: "patient",
};

test("accepts the backend bearer session payload before writing account cookies", () => {
  assert.deepEqual(accountSessionSchema.parse(validSession), validSession);
});

test("rejects session payloads that are not explicit bearer credentials", () => {
  assert.equal(accountSessionSchema.safeParse({ ...validSession, token_type: "mac" }).success, false);
  assert.equal(accountSessionSchema.safeParse({ ...validSession, unexpected: true }).success, false);
});
