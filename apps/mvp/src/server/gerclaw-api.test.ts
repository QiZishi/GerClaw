import assert from "node:assert/strict";
import test from "node:test";

import { isAllowedGerclawProxyTarget, isGuestAllowedGerclawProxyTarget } from "./gerclaw-api.ts";

const conditionId = "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911";
const alertId = "8a3e70a1-8b3a-4a9b-9e6a-0148d6e1ef3b";
const sessionId = "f177dc56-cf27-4c5f-8ebd-683d6a2d6e75";
const intakeId = "8c711e7e-7ddd-47df-8863-1a0f3d183509";
const approvalId = "8f711e7e-7ddd-47df-8863-1a0f3d183509";

test("session proxy permits only the declared session lifecycle operations", () => {
  assert.equal(isAllowedGerclawProxyTarget("sessions", "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget("sessions", "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(`sessions/${sessionId}/messages`, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(`sessions/${sessionId}`, "DELETE"), true);
  assert.equal(isAllowedGerclawProxyTarget("sessions", "PATCH"), false);
  assert.equal(isAllowedGerclawProxyTarget(`sessions/${sessionId}/messages`, "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget(`sessions/${sessionId}`, "PATCH"), false);
  assert.equal(isAllowedGerclawProxyTarget("sessions/not-a-uuid", "DELETE"), false);
});

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

test("medication reconciliation proxy permits only its owner-scoped read boundary", () => {
  const path = `clinical-intakes/${intakeId}/medication-reconciliation`;
  assert.equal(isAllowedGerclawProxyTarget(path, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(path, "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget(`clinical-intakes/${intakeId}/other`, "GET"), false);
});

test("medication review proxy permits only a caller-owned review request", () => {
  const path = `clinical-intakes/${intakeId}/medication-review-draft`;
  assert.equal(isAllowedGerclawProxyTarget(path, "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(path, "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget(`${path}/export`, "POST"), false);
});

test("prescription draft proxy permits only the caller-owned generation boundary", () => {
  const path = `clinical-intakes/${intakeId}/prescription-draft`;
  assert.equal(isAllowedGerclawProxyTarget(path, "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(path, "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget(`clinical-intakes/${intakeId}/prescription-draft/export`, "POST"), false);
});

test("prescription draft proxy permits only a bounded cancellation path", () => {
  const traceId = "trace_1234567890abcdef";
  const path = `clinical-intakes/${intakeId}/prescription-draft/${traceId}/cancel`;
  assert.equal(isAllowedGerclawProxyTarget(path, "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(path, "GET"), false);
  assert.equal(
    isAllowedGerclawProxyTarget(`clinical-intakes/${intakeId}/prescription-draft/${traceId}/finish`, "POST"),
    false
  );
  assert.equal(
    isAllowedGerclawProxyTarget(`clinical-intakes/${intakeId}/prescription-draft/trace_invalid/cancel`, "POST"),
    false
  );
});

test("prescription draft history proxy permits only an owner-scoped read", () => {
  const path = `clinical-intakes/${intakeId}/prescription-drafts`;
  assert.equal(isAllowedGerclawProxyTarget(path, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(path, "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget(`${path}/export`, "GET"), false);
});

test("skill evolution proxy permits only a caller-owned review-draft request", () => {
  assert.equal(isAllowedGerclawProxyTarget("skills/safe-followup/evolve", "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget("skills/safe-followup/evolve", "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget("skills/safe-followup/evolve/commit", "POST"), false);
});

test("Skill package preview permits only authenticated multipart submission", () => {
  assert.equal(isAllowedGerclawProxyTarget("skills/preview-upload", "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget("skills/preview-upload", "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget("skills/upload", "POST"), true);
  assert.equal(isGuestAllowedGerclawProxyTarget("skills/preview-upload", "POST"), false);
});

test("guest proxy keeps patient care flows but rejects every Skill endpoint", () => {
  assert.equal(isGuestAllowedGerclawProxyTarget("chat", "POST"), true);
  assert.equal(isGuestAllowedGerclawProxyTarget("cga/scales", "GET"), true);
  assert.equal(isGuestAllowedGerclawProxyTarget("skills", "GET"), false);
  assert.equal(isGuestAllowedGerclawProxyTarget("skills/health-education/execute", "POST"), false);
});

test("runtime approval proxy permits only a specific review or decision route", () => {
  const root = `runtime/approvals/${approvalId}`;
  assert.equal(isAllowedGerclawProxyTarget(root, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(`${root}/review`, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(`${root}/decision`, "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(`${root}/review`, "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget("runtime/approvals", "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget("runtime/approvals/not-a-uuid/review", "GET"), false);
});

test("consent proxy permits only patient-owned grant and revoke operations", () => {
  const grantId = "0f4d021b-5054-461d-88e4-109bc422f616";
  assert.equal(isAllowedGerclawProxyTarget("access-grants", "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget("access-grants", "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(`access-grants/${grantId}/revoke`, "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(`access-grants/${grantId}`, "DELETE"), false);
  assert.equal(isAllowedGerclawProxyTarget("access-grants/patients/anything", "GET"), false);
  assert.equal(isGuestAllowedGerclawProxyTarget("access-grants", "GET"), false);
  assert.equal(isGuestAllowedGerclawProxyTarget(`access-grants/${grantId}/revoke`, "POST"), false);
});

test("consent proxy exposes only the declared doctor directory and projections after account authentication", () => {
  const patientActorId = "usr_account_aabbccddeeff00112233445566778899";
  const draftId = "0f4d021b-5054-461d-88e4-109bc422f616";
  const path = `access-grants/patients/${patientActorId}/prescription-drafts`;
  const cgaPath = `access-grants/patients/${patientActorId}/cga-reports`;
  const profilePath = `access-grants/patients/${patientActorId}/health-profile`;
  assert.equal(isAllowedGerclawProxyTarget("access-grants/patients", "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget("access-grants/patients", "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget(path, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(`${path}/${draftId}/reviews`, "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget(`${path}/${draftId}/reviews`, "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget(cgaPath, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(cgaPath, "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget(profilePath, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(profilePath, "POST"), false);
  assert.equal(isGuestAllowedGerclawProxyTarget(path, "GET"), false);
  assert.equal(isGuestAllowedGerclawProxyTarget("access-grants/patients", "GET"), false);
  assert.equal(isGuestAllowedGerclawProxyTarget(cgaPath, "GET"), false);
  assert.equal(isGuestAllowedGerclawProxyTarget(profilePath, "GET"), false);
});

test("CGA proxy permits only caller-owned descriptive comparison reads", () => {
  assert.equal(isAllowedGerclawProxyTarget(`cga/assessments/${sessionId}/comparison`, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(`cga/assessments/${sessionId}/comparison`, "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget("cga/assessments/not-a-uuid/comparison", "GET"), false);
});

test("memory proxy permits only caller-owned immutable history reads", () => {
  const factId = "e7f234c4-50cb-4c6f-b556-05cc840912c0";
  assert.equal(isAllowedGerclawProxyTarget(`memory/facts/${factId}/history`, "GET"), true);
  assert.equal(isAllowedGerclawProxyTarget(`memory/facts/${factId}/history`, "POST"), false);
  assert.equal(isAllowedGerclawProxyTarget("memory/facts/not-a-uuid/history", "GET"), false);
});

test("RAG proxy permits only the bounded evidence retrieval request", () => {
  assert.equal(isAllowedGerclawProxyTarget("rag/retrieve", "POST"), true);
  assert.equal(isAllowedGerclawProxyTarget("rag/retrieve", "GET"), false);
  assert.equal(isAllowedGerclawProxyTarget("rag/retrieve/export", "POST"), false);
});
