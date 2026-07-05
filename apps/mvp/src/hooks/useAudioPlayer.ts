"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { synthesizeSpeech } from "@/services/voice/tts";

interface UseAudioPlayerReturn {
  isPlaying: boolean;
  isLoading: boolean;
  play: (text: string) => void;
  stop: () => void;
}

export function useAudioPlayer(): UseAudioPlayerReturn {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const cleanup = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  const play = useCallback(async (text: string) => {
    cleanup();
    setIsLoading(true);
    setIsPlaying(false);

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const audioBlob = await synthesizeSpeech(text, signal);

      if (signal.aborted) return;

      const url = URL.createObjectURL(audioBlob);
      objectUrlRef.current = url;

      const audio = new Audio(url);
      audioRef.current = audio;

      audio.oncanplaythrough = () => {
        if (signal.aborted) return;
        setIsLoading(false);
        setIsPlaying(true);
        audio.play().catch((err) => {
          console.error("Audio play error:", err);
          setIsPlaying(false);
          setIsLoading(false);
        });
      };

      audio.onended = () => {
        setIsPlaying(false);
        setIsLoading(false);
      };

      audio.onerror = () => {
        console.error("Audio playback error");
        setIsPlaying(false);
        setIsLoading(false);
      };

      audio.load();
    } catch (err) {
      if (signal.aborted) return;
      const error = err instanceof Error ? err.message : String(err);
      if (error !== "Aborted" && error !== "The user aborted a request.") {
        console.error("TTS synthesis error:", err);
      }
      setIsPlaying(false);
      setIsLoading(false);
    }
  }, [cleanup]);

  const stop = useCallback(() => {
    cleanup();
    setIsPlaying(false);
    setIsLoading(false);
  }, [cleanup]);

  return {
    isPlaying,
    isLoading,
    play,
    stop,
  };
}
