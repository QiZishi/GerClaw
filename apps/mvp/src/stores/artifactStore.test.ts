import assert from "node:assert/strict";
import test from "node:test";

import type { ArtifactDraftSource } from "../components/artifact/artifact-draft.ts";
import { useArtifactStore } from "./artifactStore.ts";

function draft(requestId: string): ArtifactDraftSource {
  return {
    requestId,
    messageId: `message-${requestId}`,
    sessionId: `session-${requestId}`,
    runId: null,
    title: `文档 ${requestId}`,
    markdown: `# 文档 ${requestId}`,
  };
}

test("a dirty draft cannot be replaced without explicit confirmation", () => {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  let confirmations = 0;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      confirm: () => {
        confirmations += 1;
        return false;
      },
    },
  });
  try {
    const first = draft("one");
    useArtifactStore.setState({ source: first, dirty: true });

    assert.equal(useArtifactStore.getState().openDraft(draft("two")), false);
    assert.equal(useArtifactStore.getState().source, first);
    assert.equal(useArtifactStore.getState().dirty, true);
    assert.equal(confirmations, 1);
  } finally {
    useArtifactStore.getState().clear();
    if (originalWindow) {
      Object.defineProperty(globalThis, "window", originalWindow);
    } else {
      Reflect.deleteProperty(globalThis, "window");
    }
  }
});

test("confirmed replacement clears the previous dirty state", () => {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { confirm: () => true },
  });
  try {
    useArtifactStore.setState({ source: draft("one"), dirty: true });
    const next = draft("two");

    assert.equal(useArtifactStore.getState().openDraft(next), true);
    assert.equal(useArtifactStore.getState().source, next);
    assert.equal(useArtifactStore.getState().dirty, false);
  } finally {
    useArtifactStore.getState().clear();
    if (originalWindow) {
      Object.defineProperty(globalThis, "window", originalWindow);
    } else {
      Reflect.deleteProperty(globalThis, "window");
    }
  }
});
