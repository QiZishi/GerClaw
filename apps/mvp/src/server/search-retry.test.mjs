import assert from "node:assert/strict";
import test from "node:test";

import {
  SearchRequestError,
  statusIsRetryable,
  withPrimaryFallback,
  withTransientRetry,
} from "./search-retry.ts";

test("only transient HTTP statuses are retryable", () => {
  assert.equal(statusIsRetryable(401), false);
  assert.equal(statusIsRetryable(403), false);
  assert.equal(statusIsRetryable(422), false);
  assert.equal(statusIsRetryable(408), true);
  assert.equal(statusIsRetryable(429), true);
  assert.equal(statusIsRetryable(503), true);
});

test("non-transient provider failures are attempted once", async () => {
  let calls = 0;
  await assert.rejects(
    withTransientRetry(async () => {
      calls += 1;
      throw new SearchRequestError("unauthorized", false);
    }),
    /unauthorized/
  );
  assert.equal(calls, 1);
});

test("both provider adapters can retry one transient failure", async () => {
  let anySearchCalls = 0;
  const anySearch = await withTransientRetry(async () => {
    anySearchCalls += 1;
    if (anySearchCalls === 1) throw new SearchRequestError("timeout", true);
    return "anysearch";
  });
  assert.equal(anySearch, "anysearch");
  assert.equal(anySearchCalls, 2);

  let tavilyCalls = 0;
  const tavily = await withTransientRetry(async () => {
    tavilyCalls += 1;
    if (tavilyCalls === 1) throw new SearchRequestError("rate limited", true);
    return "tavily";
  });
  assert.equal(tavily, "tavily");
  assert.equal(tavilyCalls, 2);
});

test("401 falls back immediately and Tavily retries one transient failure", async () => {
  let anySearchCalls = 0;
  let tavilyCalls = 0;
  const routed = await withPrimaryFallback(
    async () => {
      anySearchCalls += 1;
      throw new SearchRequestError("unauthorized", false);
    },
    async () => {
      tavilyCalls += 1;
      if (tavilyCalls === 1) throw new SearchRequestError("unavailable", true);
      return "tavily-result";
    }
  );
  assert.deepEqual(routed, { value: "tavily-result", fallbackUsed: true });
  assert.equal(anySearchCalls, 1);
  assert.equal(tavilyCalls, 2);
});
