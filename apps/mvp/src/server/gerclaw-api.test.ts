import assert from "node:assert/strict";
import test from "node:test";

import { isAllowedGerclawProxyTarget } from "./gerclaw-api.ts";

const conditionId = "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911";
const alertId = "8a3e70a1-8b3a-4a9b-9e6a-0148d6e1ef3b";

test("chronic-care proxy only exposes the measurement ledger routes", () => {
  assert.equal(isAllowedGerclawProxyTarget("chronic-care/conditions", "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget("chronic-care/conditions", "POST"), true);
  assert.equal(
    isAllowedGerclawProxyTarget(`chronic-care/conditions/${conditionId}/measurements`, "GET"),
    true
  );
  assert.equal(
    isAllowedGerclawProxyTarget(`chronic-care/conditions/${conditionId}/measurements`, "POST"),
    true
  );
  assert.equal(
    isAllowedGerclawProxyTarget(`chronic-care/conditions/${conditionId}/trends`, "GET"),
    true
  );
});

test("chronic-care proxy rejects unsupported methods and paths", () => {
  assert.equal(isAllowedGerclawProxyTarget("chronic-care/conditions", "DELETE"), false);
  assert.equal(
    isAllowedGerclawProxyTarget(`chronic-care/conditions/${conditionId}/trends`, "POST"),
    false
  );
  assert.equal(isAllowedGerclawProxyTarget("chronic-care/conditions/not-a-uuid/measurements", "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget("chronic-care/conditions/../memory/profile", "GET"), false);
});

test("risk-alert proxy exposes only own-alert read and acknowledgement routes", () => {
  assert.equal(isAllowedGerclawProxyTarget("risk-alerts", "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget("risk-alerts", "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget(`risk-alerts/${alertId}/acknowledgements`, "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(`risk-alerts/${alertId}/acknowledgements`, "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget(`risk-alerts/${alertId}/details`, "GET"), false);
});

test("voice proxy only exposes the governed FastAPI ASR and TTS boundaries", () => {
  assert.equal(isAllowedGerclawProxyTarget("voice/asr", "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget("voice/tts", "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget("voice/asr", "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget("voice/unknown", "POST"), false);
});
