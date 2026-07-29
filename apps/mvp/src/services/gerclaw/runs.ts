import { gerclawRequest } from "./client";
import {
  agentRunSchema,
  answerVersionListSchema,
  answerVersionSchema,
  answerVersionSelectSchema,
  artifactDeletedSchema,
  artifactListSchema,
  artifactSchema,
  artifactWriteSchema,
  feedbackReconcileSchema,
  feedbackStateSchema,
  runEventPageSchema,
  type AgentRun,
  type AnswerVersion,
  type Artifact,
  type ArtifactWrite,
  type FeedbackState,
  type RunEventPage,
} from "./run-contract";

const pathId = (value: string): string => encodeURIComponent(value);

export function readAgentRun(runId: string): Promise<AgentRun> {
  return gerclawRequest(`runs/${pathId(runId)}`, agentRunSchema);
}

export function replayAgentRunEvents(
  runId: string,
  afterSequence = 0,
  limit = 200
): Promise<RunEventPage> {
  const query = new URLSearchParams({
    after_sequence: String(afterSequence),
    limit: String(limit),
  });
  return gerclawRequest(`runs/${pathId(runId)}/events?${query}`, runEventPageSchema);
}

export function cancelAgentRun(runId: string): Promise<AgentRun> {
  return gerclawRequest(`runs/${pathId(runId)}/cancel`, agentRunSchema, {
    method: "POST",
  });
}

export function readAnswerVersions(runId: string) {
  return gerclawRequest(`runs/${pathId(runId)}/answer-versions`, answerVersionListSchema);
}

export function selectAnswerVersion(
  runId: string,
  versionId: string,
  expectedCurrentVersionId: string
): Promise<AnswerVersion> {
  return gerclawRequest(
    `runs/${pathId(runId)}/answer-versions/${pathId(versionId)}/current`,
    answerVersionSchema,
    {
      method: "PUT",
      body: JSON.stringify(
        answerVersionSelectSchema.parse({
          expected_current_version_id: expectedCurrentVersionId,
        })
      ),
    }
  );
}

export function createRunArtifact(runId: string, input: ArtifactWrite): Promise<Artifact> {
  const payload = artifactWriteSchema.parse(input);
  return gerclawRequest(`runs/${pathId(runId)}/artifacts`, artifactSchema, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function readRunArtifact(artifactId: string): Promise<Artifact> {
  return gerclawRequest(`artifacts/${pathId(artifactId)}`, artifactSchema);
}

export function readConversationArtifacts(conversationId: string) {
  return gerclawRequest(
    `conversations/${pathId(conversationId)}/artifacts`,
    artifactListSchema
  );
}

export function updateRunArtifact(
  artifactId: string,
  input: ArtifactWrite & { expected_revision: number }
): Promise<Artifact> {
  const payload = artifactWriteSchema.parse(input);
  return gerclawRequest(`artifacts/${pathId(artifactId)}`, artifactSchema, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteRunArtifact(artifactId: string, expectedRevision: number) {
  const query = new URLSearchParams({ expected_revision: String(expectedRevision) });
  return gerclawRequest(
    `artifacts/${pathId(artifactId)}?${query}`,
    artifactDeletedSchema,
    { method: "DELETE" }
  );
}

export function readRunFeedback(runId: string): Promise<FeedbackState | null> {
  return gerclawRequest(
    `runs/${pathId(runId)}/feedback`,
    feedbackStateSchema.nullable()
  );
}

export function reconcileRunFeedback(
  runId: string,
  value: -1 | 0 | 1,
  expectedRevision: number
): Promise<FeedbackState> {
  const payload = feedbackReconcileSchema.parse({
    value,
    expected_revision: expectedRevision,
  });
  return gerclawRequest(`runs/${pathId(runId)}/feedback`, feedbackStateSchema, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
