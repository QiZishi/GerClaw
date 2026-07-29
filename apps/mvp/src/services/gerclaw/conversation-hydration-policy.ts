/**
 * Server history may hydrate an empty local session, but it must never replace
 * messages that were added while the history request was in flight.
 */
export function canHydrateConversationHistory(localMessageCount: number): boolean {
  return localMessageCount === 0;
}
