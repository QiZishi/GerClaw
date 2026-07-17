/** Minimal manifest shape needed to resolve immutable CGA audio assets. */
export interface CgaAudioManifestEntry {
  scale_id: string;
  definition_version: string;
  question_id: string;
  question: { path: string };
  options: readonly { ordinal: number; audio: { path: string } }[];
}

function entryFor(
  entries: readonly CgaAudioManifestEntry[],
  scaleId: string,
  definitionVersion: string,
  questionId: string
): CgaAudioManifestEntry | undefined {
  return entries.find(
    (entry) =>
      entry.scale_id === scaleId &&
      entry.definition_version === definitionVersion &&
      entry.question_id === questionId
  );
}

/** Resolve only the published question asset for the exact scale version. */
export function resolveCgaQuestionAudio(
  entries: readonly CgaAudioManifestEntry[],
  scaleId: string,
  definitionVersion: string,
  questionId: string
): string | null {
  return entryFor(entries, scaleId, definitionVersion, questionId)?.question.path ?? null;
}

/** Resolve an answer by its server-defined ordinal, never by mutable label text. */
export function resolveCgaOptionAudio(
  entries: readonly CgaAudioManifestEntry[],
  scaleId: string,
  definitionVersion: string,
  questionId: string,
  optionOrdinal: number
): string | null {
  if (!Number.isInteger(optionOrdinal) || optionOrdinal < 0) return null;
  return entryFor(entries, scaleId, definitionVersion, questionId)?.options.find(
    (option) => option.ordinal === optionOrdinal
  )?.audio.path ?? null;
}
