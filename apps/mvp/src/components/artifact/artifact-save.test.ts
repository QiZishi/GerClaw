import assert from "node:assert/strict";
import test from "node:test";

import {
  artifactMatchesDraft,
  artifactSaveFailure,
  latestArtifactForRun,
} from "./artifact-save.ts";
import type { Artifact } from "../../services/gerclaw/run-contract.ts";

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

test("artifact recovery selects the newest revision for the producing run", () => {
  const base: Artifact = {
    schema_version: "1.0",
    id: "00000000-0000-4000-8000-000000000001",
    run_id: "00000000-0000-4000-8000-000000000100",
    conversation_id: "00000000-0000-4000-8000-000000000200",
    title: "初稿",
    markdown: "初稿",
    kind: "markdown",
    revision: 1,
    saved: true,
    created_at: "2026-07-30T01:00:00Z",
    updated_at: "2026-07-30T01:00:00Z",
  };
  const newest = {
    ...base,
    id: "00000000-0000-4000-8000-000000000002",
    revision: 2,
    title: "修订稿",
    updated_at: "2026-07-30T02:00:00Z",
  };
  assert.equal(
    latestArtifactForRun([base, newest], base.run_id)?.title,
    "修订稿",
  );
  assert.equal(
    latestArtifactForRun([base], "00000000-0000-4000-8000-000000000999"),
    null,
  );
});
