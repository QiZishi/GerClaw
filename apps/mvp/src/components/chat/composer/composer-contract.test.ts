import assert from "node:assert/strict";
import test from "node:test";

import { shouldSubmitComposerKey } from "./composer-contract.ts";
import { documentMediaType } from "./document-media.ts";

const baseKey = {
  key: "Enter",
  shiftKey: false,
  isComposing: false,
  keyCode: 13,
  isRecording: false,
  isTranscribing: false,
};

test("composer sends only a plain Enter outside IME and voice states", () => {
  assert.equal(shouldSubmitComposerKey(baseKey), true);
  assert.equal(shouldSubmitComposerKey({ ...baseKey, shiftKey: true }), false);
  assert.equal(shouldSubmitComposerKey({ ...baseKey, isComposing: true }), false);
  assert.equal(shouldSubmitComposerKey({ ...baseKey, keyCode: 229 }), false);
  assert.equal(shouldSubmitComposerKey({ ...baseKey, isRecording: true }), false);
});

test("document media type uses validated MIME or bounded extension fallback", () => {
  assert.equal(documentMediaType({ type: "application/pdf", name: "record.bin" }), "application/pdf");
  assert.equal(documentMediaType({ type: "", name: "notes.md" }), "text/markdown");
  assert.equal(documentMediaType({ type: "", name: "unsafe.exe" }), null);
});
