import assert from "node:assert/strict";
import test from "node:test";

import { GUEST_ACCESS_COOKIE, resolveGerclawAccess } from "./gerclaw-access.ts";

test("guest access is stable within one browser session without becoming persistent history", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiUrl = process.env.GERCLAW_API_URL;
  const originalSecret = process.env.GERCLAW_GUEST_IDENTITY_SECRET;
  let issuedCredentials = 0;
  process.env.GERCLAW_API_URL = "https://api.example.test";
  process.env.GERCLAW_GUEST_IDENTITY_SECRET = "g".repeat(32);
  globalThis.fetch = async () => {
    issuedCredentials += 1;
    return new Response(
      JSON.stringify({ access_token: "a".repeat(32), expires_in: 3_600 }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };

  try {
    const first = await resolveGerclawAccess(new Request("https://mvp.example.test/api/gerclaw/chat"));
    const response = new Response();
    first.applyCookies(response);
    const setCookie = response.headers.get("set-cookie") ?? "";
    assert.match(setCookie, new RegExp(`^${GUEST_ACCESS_COOKIE}=`));
    assert.doesNotMatch(setCookie, /Max-Age=/i);
    assert.equal(issuedCredentials, 1);

    const guestToken = setCookie.match(new RegExp(`${GUEST_ACCESS_COOKIE}=([^;]+)`))?.[1];
    assert.ok(guestToken);
    const second = await resolveGerclawAccess(
      new Request("https://mvp.example.test/api/gerclaw/chat", {
        headers: { cookie: `${GUEST_ACCESS_COOKIE}=${guestToken}` },
      }),
    );
    assert.equal(second.accessToken, first.accessToken);
    assert.equal(issuedCredentials, 1);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiUrl === undefined) delete process.env.GERCLAW_API_URL;
    else process.env.GERCLAW_API_URL = originalApiUrl;
    if (originalSecret === undefined) delete process.env.GERCLAW_GUEST_IDENTITY_SECRET;
    else process.env.GERCLAW_GUEST_IDENTITY_SECRET = originalSecret;
  }
});
