import type { AnswerVersion } from "@/services/gerclaw/run-contract";

export function orderedAnswerVersions(versions: AnswerVersion[]): AnswerVersion[] {
  return [...versions].sort((left, right) => left.version - right.version);
}

export function adjacentAnswerVersion(
  versions: AnswerVersion[],
  currentId: string,
  direction: -1 | 1,
): AnswerVersion | null {
  const ordered = orderedAnswerVersions(versions);
  const currentIndex = ordered.findIndex((version) => version.id === currentId);
  if (currentIndex < 0) return null;
  return ordered[currentIndex + direction] ?? null;
}
