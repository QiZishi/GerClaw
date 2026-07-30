import type { Artifact } from "@/services/gerclaw/run-contract";

export interface ArtifactDraftValue {
  title: string;
  markdown: string;
}

export type ArtifactSaveStatus =
  | "creating"
  | "dirty"
  | "saving"
  | "saved"
  | "local-only"
  | "error"
  | "conflict";

export function artifactMatchesDraft(
  artifact: Pick<Artifact, "title" | "markdown">,
  draft: ArtifactDraftValue,
): boolean {
  return artifact.title === draft.title && artifact.markdown === draft.markdown;
}

export function latestArtifactForRun(
  artifacts: Artifact[],
  runId: string,
): Artifact | null {
  return (
    artifacts
      .filter((artifact) => artifact.run_id === runId)
      .sort(
        (left, right) =>
          right.revision - left.revision ||
          Date.parse(right.updated_at) - Date.parse(left.updated_at),
      )[0] ?? null
  );
}

export function artifactSaveFailure(error: unknown): {
  status: Extract<ArtifactSaveStatus, "error" | "conflict">;
  message: string;
} {
  if (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    error.status === 409
  ) {
    return {
      status: "conflict",
      message: "文档已在其他窗口更新。请复制当前修改后重新打开，避免覆盖较新的版本。",
    };
  }
  return {
    status: "error",
    message: "自动保存失败。请检查网络后重试，当前修改仍保留在本页。",
  };
}
