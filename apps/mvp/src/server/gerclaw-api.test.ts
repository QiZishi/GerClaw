import assert from "node:assert/strict";
import test from "node:test";

import { isAllowedGerclawProxyTarget } from "./gerclaw-api.ts";

const conditionId = "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911";

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
