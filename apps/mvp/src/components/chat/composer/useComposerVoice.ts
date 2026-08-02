"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from "react";

import { toast } from "@/components/ui/toast";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { recognizeAudio } from "@/services/voice/asr";

interface ComposerVoiceOptions {
  textAreaRef: RefObject<HTMLTextAreaElement | null>;
  setText: Dispatch<SetStateAction<string>>;
  isOnline: boolean;
  asrAvailable: boolean;
  isGenerating: boolean;
  isSending: boolean;
}

export function useComposerVoice({
  textAreaRef,
  setText,
  isOnline,
  asrAvailable,
  isGenerating,
  isSending,
}: ComposerVoiceOptions) {
  const [isTranscribing, setIsTranscribing] = useState(false);
  const transcriptionControllerRef = useRef<AbortController | null>(null);
  const {
    isRecording,
    recordingDuration,
    audioLevel,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useAudioRecorder();
  const micDisabled =
    !isOnline || !asrAvailable || isTranscribing || isGenerating || isSending;

  useEffect(() => () => {
    transcriptionControllerRef.current?.abort();
  }, []);

  const resetVoice = useCallback(() => {
    transcriptionControllerRef.current?.abort();
    transcriptionControllerRef.current = null;
    setIsTranscribing(false);
    cancelRecording();
  }, [cancelRecording]);

  const startVoice = useCallback(async () => {
    if (isTranscribing || isGenerating) return;
    try {
      await startRecording();
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "无法启动录音");
    }
  }, [isGenerating, isTranscribing, startRecording]);

  const cancelVoice = useCallback(() => {
    try {
      cancelRecording();
    } catch {
      toast.show("取消录音失败");
    }
  }, [cancelRecording]);

  const cancelTranscription = useCallback(() => {
    const controller = transcriptionControllerRef.current;
    if (!controller) return;
    controller.abort();
    transcriptionControllerRef.current = null;
    setIsTranscribing(false);
    toast.show("已取消语音识别，您可以继续编辑或重新录音。");
  }, []);

  const finishVoice = useCallback(async () => {
    try {
      const blob = await stopRecording();
      const controller = new AbortController();
      transcriptionControllerRef.current = controller;
      setIsTranscribing(true);
      try {
        const recognizedText = await recognizeAudio(blob, controller.signal);
        if (!controller.signal.aborted && recognizedText) {
          setText((current) => `${current}${current ? " " : ""}${recognizedText}`);
          window.setTimeout(() => {
            const textArea = textAreaRef.current;
            if (!textArea) return;
            textArea.style.height = "auto";
            textArea.style.height = `${Math.max(52, Math.min(textArea.scrollHeight, 200))}px`;
            textArea.focus();
          }, 50);
        }
      } catch {
        if (!controller.signal.aborted) toast.show("语音识别失败，请重试");
      } finally {
        if (transcriptionControllerRef.current === controller) {
          transcriptionControllerRef.current = null;
          setIsTranscribing(false);
        }
      }
    } catch {
      toast.show("录音失败，请重试");
    }
  }, [setText, stopRecording, textAreaRef]);

  return {
    isRecording,
    recordingDuration,
    audioLevel,
    isTranscribing,
    micDisabled,
    resetVoice,
    startVoice,
    cancelVoice,
    finishVoice,
    cancelTranscription,
  };
}

export function formatRecordingDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}
