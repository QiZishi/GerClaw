import assert from "node:assert/strict";
import test from "node:test";

import {
  artifactMatchesDraft,
  artifactSaveFailure,
} from "./artifact-save.ts";

test("artifact equality includes both title and Markdown", () => {
  const artifact = { title: "随访建议", markdown: "- 记录血压" };
  assert.equal(artifactMatchesDraft(artifact, artifact), true);
  assert.equal(
    artifactMatchesDraft(artifact, { ...artifact, title: "新的标题" }),
    false,
  );
  assert.equal(
    artifactMatchesDraft(artifact, { ...artifact, markdown: "- 记录血糖" }),
    false,
  );
});

test("save failures expose bounded reader-facing messages", () => {
  const conflict = artifactSaveFailure(
    { status: 409, message: "internal revision changed" },
  );
  assert.equal(conflict.status, "conflict");
  assert.equal(conflict.message.includes("internal"), false);

  const network = artifactSaveFailure(new TypeError("fetch failed with host"));
  assert.equal(network.status, "error");
  assert.equal(network.message.includes("host"), false);
});
