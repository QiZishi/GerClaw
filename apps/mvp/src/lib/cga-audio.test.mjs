import assert from "node:assert/strict";
import test from "node:test";
import { resolveCgaOptionAudio, resolveCgaQuestionAudio } from "./cga-audio-resolver.ts";

const manifest = [{
  scale_id: "phq9",
  definition_version: "2026-07-16",
  question_id: "phq9_1",
  question: { path: "/audio/cga/phq9/2026-07-16/questions/phq9_1.wav" },
  options: [{ ordinal: 0, audio: { path: "/audio/cga/phq9/2026-07-16/options/first.wav" } }],
}];

test("CGA question and option playback require the exact published definition version", () => {
  assert.equal(
    resolveCgaQuestionAudio(manifest, "phq9", "2026-07-16", "phq9_1"),
    "/audio/cga/phq9/2026-07-16/questions/phq9_1.wav"
  );
  assert.equal(
    resolveCgaOptionAudio(manifest, "phq9", "2026-07-16", "phq9_1", 0),
    "/audio/cga/phq9/2026-07-16/options/first.wav"
  );
  assert.equal(resolveCgaOptionAudio(manifest, "phq9", "2026-07-16", "phq9_1", 4), null);
  assert.equal(resolveCgaQuestionAudio(manifest, "phq9", "unknown-version", "phq9_1"), null);
  assert.equal(resolveCgaOptionAudio(manifest, "phq9", "unknown-version", "phq9_1", 0), null);
});
