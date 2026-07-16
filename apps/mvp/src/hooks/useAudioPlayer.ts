"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { synthesizeSpeech } from "@/services/voice/tts";
import { splitTtsText } from "@/lib/tts-text";
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
  const queueRef = useRef<string[]>([]);
  const totalCharactersRef = useRef(0);
  const completedCharactersRef = useRef(0);
  const playbackIdRef = useRef(0);
  const playNextRef = useRef<(playbackId: number) => Promise<void>>(async () => undefined);

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
    playbackIdRef.current += 1;
    queueRef.current = [];
    totalCharactersRef.current = 0;
    completedCharactersRef.current = 0;
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

  const playNext = useCallback(async (playbackId: number) => {
    if (playbackId !== playbackIdRef.current) return;
    const chunk = queueRef.current.shift();
    if (!chunk) {
      stop();
      return;
    }

    if (audioRef.current?.ended) {
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setIsLoading(true);
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      const audioBlob = await synthesizeSpeech(chunk, controller.signal);
      if (controller.signal.aborted || playbackId !== playbackIdRef.current) return;

      const url = URL.createObjectURL(audioBlob);
      objectUrlRef.current = url;
      const audio = new Audio(url);
      audio.preload = "auto";
      audioRef.current = audio;
      audio.onerror = () => stop();
      audio.onplay = () => {
        if (audioRef.current !== audio || playbackId !== playbackIdRef.current) return;
        setIsLoading(false);
        setIsPlaying(true);
        setIsPaused(false);
      };
      audio.onpause = () => {
        if (audioRef.current !== audio || audio.ended || playbackId !== playbackIdRef.current) return;
        setIsPlaying(false);
        setIsPaused(true);
      };
      const syncProgress = () => {
        if (audioRef.current !== audio || playbackId !== playbackIdRef.current) return;
        const total = totalCharactersRef.current;
        if (!total || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
        const current = Math.max(0, Math.min(1, audio.currentTime / audio.duration));
        setProgress(Math.max(0, Math.min(1, (completedCharactersRef.current + chunk.length * current) / total)));
      };
      audio.ontimeupdate = syncProgress;
      audio.ondurationchange = syncProgress;
      audio.onended = () => {
        if (playbackId !== playbackIdRef.current) return;
        completedCharactersRef.current += chunk.length;
        setProgress(Math.min(1, completedCharactersRef.current / totalCharactersRef.current));
        void playNextRef.current(playbackId);
      };
      await audio.play();
      syncProgress();
    } catch (error) {
      if (!controller.signal.aborted && playbackId === playbackIdRef.current) {
        stop();
        throw error;
      }
    }
  }, [stop]);

  useEffect(() => {
    playNextRef.current = playNext;
  }, [playNext]);

  const play = useCallback(async (text: string) => {
    claimPlayer();
    const chunks = splitTtsText(text);
    if (chunks.length === 0) return;
    queueRef.current = chunks;
    totalCharactersRef.current = chunks.reduce((total, chunk) => total + chunk.length, 0);
    completedCharactersRef.current = 0;
    setProgress(0);
    await playNext(playbackIdRef.current);
  }, [claimPlayer, playNext]);

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
