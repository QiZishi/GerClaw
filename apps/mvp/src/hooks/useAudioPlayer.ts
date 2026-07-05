"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { streamTTS } from "@/services/voice/tts";

const TTS_SAMPLE_RATE = 24000;
const BUFFER_THRESHOLD_SAMPLES = Math.floor(TTS_SAMPLE_RATE * 0.1);

interface UseAudioPlayerReturn {
  isPlaying: boolean;
  isPaused: boolean;
  isLoading: boolean;
  play: (text: string) => void;
  pause: () => void;
  stop: () => void;
}

export function useAudioPlayer(): UseAudioPlayerReturn {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const audioContextRef = useRef<AudioContext | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const bufferQueueRef = useRef<Int16Array[]>([]);
  const totalBufferedRef = useRef(0);
  const startedPlayingRef = useRef(false);
  const nextTimeRef = useRef(0);
  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const isStoppingRef = useRef(false);

  const cleanup = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    sourcesRef.current.forEach((source) => {
      try {
        source.stop();
      } catch {
        // ignore
      }
    });
    sourcesRef.current = [];

    bufferQueueRef.current = [];
    totalBufferedRef.current = 0;
    startedPlayingRef.current = false;
    nextTimeRef.current = 0;
    isStoppingRef.current = false;
  }, []);

  useEffect(() => {
    return () => {
      cleanup();
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
        audioContextRef.current = null;
      }
    };
  }, [cleanup]);

  const playBufferChunk = useCallback((ctx: AudioContext, pcmData: Int16Array) => {
    const float32Data = new Float32Array(pcmData.length);
    for (let i = 0; i < pcmData.length; i++) {
      float32Data[i] = pcmData[i] / 32768;
    }

    const audioBuffer = ctx.createBuffer(1, float32Data.length, TTS_SAMPLE_RATE);
    audioBuffer.getChannelData(0).set(float32Data);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    sourcesRef.current.push(source);

    const currentTime = ctx.currentTime;
    const startTime = Math.max(nextTimeRef.current, currentTime + 0.05);
    source.start(startTime);
    nextTimeRef.current = startTime + audioBuffer.duration;

    source.onended = () => {
      sourcesRef.current = sourcesRef.current.filter((s) => s !== source);
      if (sourcesRef.current.length === 0 && bufferQueueRef.current.length === 0 && !isStoppingRef.current) {
        setIsPlaying(false);
        setIsPaused(false);
        setIsLoading(false);
      }
    };
  }, []);

  const flushBuffer = useCallback(() => {
    const ctx = audioContextRef.current;
    if (!ctx) return;

    while (bufferQueueRef.current.length > 0 && totalBufferedRef.current > 0) {
      const chunk = bufferQueueRef.current.shift()!;
      totalBufferedRef.current -= chunk.length;
      playBufferChunk(ctx, chunk);
    }
  }, [playBufferChunk]);

  const play = useCallback((text: string) => {
    cleanup();
    isStoppingRef.current = false;
    setIsLoading(true);
    setIsPlaying(true);
    setIsPaused(false);

    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext({ sampleRate: TTS_SAMPLE_RATE });
    }

    const ctx = audioContextRef.current;
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }

    nextTimeRef.current = ctx.currentTime;
    bufferQueueRef.current = [];
    totalBufferedRef.current = 0;
    startedPlayingRef.current = false;

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    streamTTS(
      text,
      {
        onAudioChunk: (pcm) => {
          if (signal.aborted || isStoppingRef.current) return;

          bufferQueueRef.current.push(pcm);
          totalBufferedRef.current += pcm.length;

          if (!startedPlayingRef.current && totalBufferedRef.current >= BUFFER_THRESHOLD_SAMPLES) {
            startedPlayingRef.current = true;
            setIsLoading(false);
            flushBuffer();
          } else if (startedPlayingRef.current) {
            flushBuffer();
          }
        },
        onDone: () => {
          if (isStoppingRef.current) return;
          if (bufferQueueRef.current.length > 0) {
            flushBuffer();
          } else if (sourcesRef.current.length === 0) {
            setIsPlaying(false);
            setIsLoading(false);
            setIsPaused(false);
          }
        },
        onError: (err) => {
          console.error("TTS error:", err);
          setIsPlaying(false);
          setIsLoading(false);
          setIsPaused(false);
          cleanup();
        },
      },
      signal
    );
  }, [cleanup, flushBuffer]);

  const pause = useCallback(() => {
    const ctx = audioContextRef.current;
    if (ctx && isPlaying && !isPaused) {
      ctx.suspend().catch(() => {});
      setIsPaused(true);
    } else if (ctx && isPaused) {
      ctx.resume().catch(() => {});
      setIsPaused(false);
    }
  }, [isPlaying, isPaused]);

  const stop = useCallback(() => {
    isStoppingRef.current = true;
    cleanup();
    setIsPlaying(false);
    setIsPaused(false);
    setIsLoading(false);
  }, [cleanup]);

  return {
    isPlaying,
    isPaused,
    isLoading,
    play,
    pause,
    stop,
  };
}
