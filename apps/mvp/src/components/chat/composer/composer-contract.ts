export interface ComposerKeyState {
  key: string;
  shiftKey: boolean;
  isComposing: boolean;
  keyCode: number;
  isRecording: boolean;
  isTranscribing: boolean;
}

export function shouldSubmitComposerKey(state: ComposerKeyState): boolean {
  return (
    state.key === "Enter"
    && !state.shiftKey
    && !state.isComposing
    && state.keyCode !== 229
    && !state.isRecording
    && !state.isTranscribing
  );
}
