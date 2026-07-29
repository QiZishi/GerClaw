export interface CitationMarkerMatch {
  fullMatch: string;
  citeId: number;
  index: number;
}

/**
 * Match only server-owned citation markers. Model-facing E/W markers are
 * normalized and range-checked by the API before terminal text reaches here.
 */
export function findCitationMatches(text: string): CitationMarkerMatch[] {
  const regex = /\[C([1-9]\d{0,2})\]/g;
  const matches: CitationMarkerMatch[] = [];
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    matches.push({
      fullMatch: match[0],
      citeId: Number.parseInt(match[1], 10),
      index: match.index,
    });
  }
  return matches;
}
