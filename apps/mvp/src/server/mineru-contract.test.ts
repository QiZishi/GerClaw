import assert from "node:assert/strict";
import test from "node:test";

import {
  assertAllowedProviderUrl,
  PayloadLimitError,
  parsePollResponse,
  parseSubmitResponse,
  readStreamWithLimit,
} from "./mineru-contract.ts";

const allowedHosts = new Set(["mineru.example", "uploads.example"]);

test("accepts a valid signed upload response", () => {
  assert.deepEqual(
    parseSubmitResponse({
      code: 0,
      data: { task_id: "task-1", file_url: "https://uploads.example/signed" },
    }),
    { taskId: "task-1", fileUrl: "https://uploads.example/signed" }
  );
});

test("rejects malformed or unsuccessful provider responses", () => {
  assert.throws(() => parseSubmitResponse({ code: 1, data: {} }), /invalid/);
  assert.throws(() => parsePollResponse({ code: 0, data: { state: "mystery" } }), /invalid/);
});

test("only allows configured HTTPS provider URLs", () => {
  assert.equal(
    assertAllowedProviderUrl("https://mineru.example/parse/file", allowedHosts).hostname,
    "mineru.example"
  );
  assert.throws(
    () => assertAllowedProviderUrl("http://mineru.example/parse/file", allowedHosts),
    /allowlist/
  );
  assert.throws(
    () => assertAllowedProviderUrl("https://attacker.example/file", allowedHosts),
    /allowlist/
  );
});

test("keeps failed parses distinct from completed results", () => {
  assert.deepEqual(
    parsePollResponse({
      code: 0,
      data: { state: "failed", err_msg: "unsupported document" },
    }),
    { state: "failed", markdownUrl: undefined, error: "unsupported document" }
  );
});

test("bounds streamed request and provider response bodies", async () => {
  assert.equal(
    new TextDecoder().decode(await readStreamWithLimit(new Blob(["1234"]).stream(), 4)),
    "1234"
  );
  await assert.rejects(readStreamWithLimit(new Blob(["12345"]).stream(), 4), PayloadLimitError);
  await assert.rejects(readStreamWithLimit(new Blob(["x"]).stream(), 4, "999"), PayloadLimitError);
});
