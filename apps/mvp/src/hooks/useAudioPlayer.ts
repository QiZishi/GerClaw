"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { synthesizeSpeech } from "@/services/voice/tts";
import {
  claimActiveAudioPlayer,
  releaseActiveAudioPlayer,
} from "@/lib/audioPlaybackCoordinator";

interface UseAudioPlayerReturn {
  isPlaying: boolean;
  isPaused: boolean;
  isLoading: boolean;
  /** A normalized, best-effort position from the browser media element. */
  progress: number;
  play: (text: string) => Promise<void>;
  playSource: (sourceUrl: string) => Promise<void>;
  pause: () => void;
  resume: () => Promise<void>;
  stop: () => void;
}

export function useAudioPlayer(): UseAudioPlayerReturn {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const playerIdRef = useRef(Symbol("audio-player"));

  const releaseMedia = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (audioRef.current) {
      const audio = audioRef.current;
      audio.onended = null;
      audio.onerror = null;
      audio.onpause = null;
      audio.onplay = null;
      audio.ontimeupdate = null;
      audio.ondurationchange = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    releaseMedia();
    releaseActiveAudioPlayer(playerIdRef.current);
    setIsPlaying(false);
    setIsPaused(false);
    setIsLoading(false);
    setProgress(0);
  }, [releaseMedia]);

  useEffect(() => stop, [stop]);

  const claimPlayer = useCallback(() => {
    stop();
    claimActiveAudioPlayer(playerIdRef.current, stop);
    setIsLoading(true);
  }, [stop]);

  const startAudio = useCallback(async (sourceUrl: string) => {
    const audio = new Audio(sourceUrl);
    audio.preload = "auto";
    audioRef.current = audio;
    audio.onended = () => stop();
    audio.onerror = () => stop();
    audio.onplay = () => {
      if (audioRef.current !== audio) return;
      setIsLoading(false);
      setIsPlaying(true);
      setIsPaused(false);
    };
    audio.onpause = () => {
      if (audioRef.current !== audio || audio.ended) return;
      setIsPlaying(false);
      setIsPaused(true);
    };
    const syncProgress = () => {
      if (audioRef.current !== audio || !Number.isFinite(audio.duration) || audio.duration <= 0) {
        return;
      }
      setProgress(Math.max(0, Math.min(1, audio.currentTime / audio.duration)));
    };
    audio.ontimeupdate = syncProgress;
    audio.ondurationchange = syncProgress;
    await audio.play();
    if (audioRef.current !== audio) return;
    syncProgress();
  }, [stop]);

  const play = useCallback(async (text: string) => {
    claimPlayer();

    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      const audioBlob = await synthesizeSpeech(text, controller.signal);
      if (controller.signal.aborted) return;

      const url = URL.createObjectURL(audioBlob);
      objectUrlRef.current = url;
      await startAudio(url);
      if (controller.signal.aborted) return;
    } catch (error) {
      if (!controller.signal.aborted) {
        stop();
        throw error;
      }
    }
  }, [claimPlayer, startAudio, stop]);

  const playSource = useCallback(async (sourceUrl: string) => {
    claimPlayer();
    try {
      await startAudio(sourceUrl);
    } catch (error) {
      stop();
      throw error;
    }
  }, [claimPlayer, startAudio, stop]);

  const pause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || audio.paused) return;
    audio.pause();
  }, []);

  const resume = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || !isPaused) return;
    try {
      await audio.play();
      setIsPlaying(true);
      setIsPaused(false);
    } catch (error) {
      stop();
      throw error;
    }
  }, [isPaused, stop]);

  return { isPlaying, isPaused, isLoading, progress, play, playSource, pause, resume, stop };
}
