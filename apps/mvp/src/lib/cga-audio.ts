import { CGA_AUDIO_MANIFEST } from "@/generated/cgaAudioManifest";
import { resolveCgaOptionAudio, resolveCgaQuestionAudio } from "@/lib/cga-audio-resolver";
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
  return resolveCgaQuestionAudio(
    CGA_AUDIO_MANIFEST.scales,
    scaleId,
    definitionVersion,
    question.id
  );
}

/**
 * Resolve one answer option to its version-bound pre-recorded asset.
 *
 * Options are addressed by their server-defined ordinal rather than their
 * display text.  This keeps playback tied to the immutable questionnaire
 * definition and avoids matching a translated or edited label at runtime.
 */
export function recordedCgaOptionAudio(
  scaleId: CgaScaleId,
  definitionVersion: string,
  question: CgaQuestion,
  optionOrdinal: number
): string | null {
  if (!Number.isInteger(optionOrdinal) || optionOrdinal < 0) return null;
  return resolveCgaOptionAudio(
    CGA_AUDIO_MANIFEST.scales,
    scaleId,
    definitionVersion,
    question.id,
    optionOrdinal
  );
}
