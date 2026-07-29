import assert from "node:assert/strict";
import test from "node:test";

import { adjacentAnswerVersion, orderedAnswerVersions } from "./answer-version.ts";
import type { AnswerVersion } from "@/services/gerclaw/run-contract";

const makeVersion = (version: number): AnswerVersion => ({
  schema_version: "1.2",
  id: `00000000-0000-4000-8000-${String(version).padStart(12, "0")}`,
  run_id: "00000000-0000-4000-8000-000000000100",
  producer_run_id: "00000000-0000-4000-8000-000000000100",
  answer_group_id: "00000000-0000-4000-8000-000000000200",
  assistant_message_id: "00000000-0000-4000-8000-000000000300",
  version,
  is_current: version === 2,
  supersedes_id: null,
  answer_markdown: `answer ${version}`,
  citations: [],
  created_at: "2026-07-29T12:00:00Z",
});

test("answer versions are ordered and bounded navigation never wraps", () => {
  const versions = [makeVersion(3), makeVersion(1), makeVersion(2)];
  assert.deepEqual(orderedAnswerVersions(versions).map((item) => item.version), [1, 2, 3]);
  assert.equal(adjacentAnswerVersion(versions, makeVersion(2).id, -1)?.version, 1);
  assert.equal(adjacentAnswerVersion(versions, makeVersion(2).id, 1)?.version, 3);
  assert.equal(adjacentAnswerVersion(versions, makeVersion(1).id, -1), null);
});
