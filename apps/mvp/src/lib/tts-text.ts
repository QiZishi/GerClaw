const DEFAULT_TTS_CHUNK_LENGTH = 280;
const SENTENCE_BOUNDARY = /[。！？!?；;\n]/g;

/**
 * Split a long answer into natural, bounded TTS requests.  The first chunk
 * can start playing without waiting for the entire answer to synthesize.
 */
export function splitTtsText(text: string, maxLength = DEFAULT_TTS_CHUNK_LENGTH): string[] {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) return [];
  if (!Number.isInteger(maxLength) || maxLength < 40) {
    throw new RangeError("maxLength must be an integer of at least 40");
  }

  const chunks: string[] = [];
  let remaining = normalized;
  while (remaining.length > maxLength) {
    const window = remaining.slice(0, maxLength);
    let boundary = -1;
    for (const match of window.matchAll(SENTENCE_BOUNDARY)) {
      boundary = (match.index ?? -1) + match[0].length;
    }
    const end = boundary > 0 ? boundary : maxLength;
    const chunk = remaining.slice(0, end).trim();
    if (chunk) chunks.push(chunk);
    remaining = remaining.slice(end).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}
