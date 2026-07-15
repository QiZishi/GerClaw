let activePlayerId: symbol | null = null;
let stopActivePlayer: (() => void) | null = null;

/**
 * Ensures that GerClaw has exactly one active spoken response at a time.
 * It deliberately has no React dependency so a workflow-level exit control can
 * stop playback started inside a message or CGA component.
 */
export function claimActiveAudioPlayer(playerId: symbol, stop: () => void): void {
  if (stopActivePlayer && activePlayerId !== playerId) {
    stopActivePlayer();
  }
  activePlayerId = playerId;
  stopActivePlayer = stop;
}

export function releaseActiveAudioPlayer(playerId: symbol): void {
  if (activePlayerId !== playerId) return;
  activePlayerId = null;
  stopActivePlayer = null;
}

/** Stops the one globally active playback, regardless of the component that started it. */
export function stopActiveAudioPlayer(): void {
  stopActivePlayer?.();
}
