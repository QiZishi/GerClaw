import { CGA_AUDIO_MANIFEST } from "@/generated/cgaAudioManifest";
import type { CgaQuestion, CgaScaleId } from "@/services/gerclaw/schemas";

/**
 * Return only an audio asset tied to the server's immutable scale definition.
 *
 * An absent or mismatched version is intentionally treated as unavailable:
 * callers may use the live TTS accessibility fallback, but never an asset from
 * a different published questionnaire version.
 */
export function recordedCgaQuestionAudio(
  scaleId: CgaScaleId,
  definitionVersion: string,
  question: CgaQuestion
): string | null {
  const entry = CGA_AUDIO_MANIFEST.scales.find(
    (candidate) =>
      candidate.scale_id === scaleId &&
      candidate.definition_version === definitionVersion &&
      candidate.question_id === question.id
  );
  return entry?.question.path ?? null;
}
