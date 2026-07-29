export interface DurableStreamCursor {
  runId?: string;
  lastSequence: number;
}

export interface CursorMetadata {
  run_id?: string;
  sequence?: number;
}

export class DurableStreamCursorError extends Error {}

export function advanceDurableCursor(
  metadata: CursorMetadata,
  cursor: DurableStreamCursor
): boolean {
  if ((metadata.run_id === undefined) !== (metadata.sequence === undefined)) {
    throw new DurableStreamCursorError("durable cursor fields must be paired");
  }
  if (metadata.run_id === undefined || metadata.sequence === undefined) return true;
  if (cursor.runId && cursor.runId !== metadata.run_id) {
    throw new DurableStreamCursorError("durable cursor run changed");
  }
  cursor.runId = metadata.run_id;
  if (metadata.sequence <= cursor.lastSequence) return false;
  cursor.lastSequence = metadata.sequence;
  return true;
}
