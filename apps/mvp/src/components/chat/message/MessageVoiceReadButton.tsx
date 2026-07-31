"use client";

import { useEffect, useRef } from "react";
import { Pause, Play, Square, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/services/api-client";
import { useAppStore } from "@/stores/appStore";

function isTtsUnavailable(error: unknown): boolean {
  return error instanceof ApiError && error.code === "VOICE_TTS_UNAVAILABLE";
}

export function MessageVoiceReadButton({
  text,
  seniorMode,
  autoPlay,
  onAutoPlayConsumed,
}: {
  text: string;
  seniorMode: boolean;
  autoPlay: boolean;
  onAutoPlayConsumed: () => void;
}) {
  const { isPlaying, isPaused, isLoading, progress, play, pause, resume, stop } = useAudioPlayer();
  const setTtsAvailable = useAppStore((state) => state.setTtsAvailable);
  const autoPlaybackClaimedRef = useRef(false);
  const autoPlaybackTimerRef = useRef<number | null>(null);

  const reportPlaybackError = (error: unknown) => {
    if (isTtsUnavailable(error)) {
      setTtsAvailable(false);
      toast.show("语音朗读当前不可用");
      return;
    }
    toast.show("语音播放失败，请稍后重试");
  };
  const start = () =>
    void play(text)
      .then(() => setTtsAvailable(true))
      .catch(reportPlaybackError);
  const continuePlayback = () => void resume().catch(reportPlaybackError);

  useEffect(() => {
    if (!autoPlay || autoPlaybackClaimedRef.current || !text) return;
    autoPlaybackClaimedRef.current = true;
    onAutoPlayConsumed();
    autoPlaybackTimerRef.current = window.setTimeout(() => {
      autoPlaybackTimerRef.current = null;
      void play(text)
        .then(() => setTtsAvailable(true))
        .catch((error: unknown) => {
          if (isTtsUnavailable(error)) setTtsAvailable(false);
        });
    }, 500);
    return () => {
      if (!autoPlaybackClaimedRef.current && autoPlaybackTimerRef.current !== null) {
        window.clearTimeout(autoPlaybackTimerRef.current);
        autoPlaybackTimerRef.current = null;
      }
    };
  }, [autoPlay, onAutoPlayConsumed, play, setTtsAvailable, text]);

  useEffect(() => () => {
    if (autoPlaybackTimerRef.current !== null) {
      window.clearTimeout(autoPlaybackTimerRef.current);
      autoPlaybackTimerRef.current = null;
    }
    stop();
  }, [stop]);

  if (isLoading) {
    return (
      <Button
        variant="ghost"
        size={seniorMode ? "default" : "sm"}
        className={cn("gap-1.5 bg-primary/10 text-primary", seniorMode && "min-h-12 px-3 text-base")}
        onClick={stop}
        aria-label="取消语音准备"
        aria-busy="true"
      >
        <Volume2 className={seniorMode ? "size-5" : "size-4"} aria-hidden />
        <span>正在准备，点击取消</span>
      </Button>
    );
  }
  if (isPlaying || isPaused) {
    return (
      <div className="inline-flex items-center gap-1.5" role="group" aria-label="语音播放控制">
        <Button
          variant="ghost"
          size={seniorMode ? "default" : "icon-sm"}
          className={cn("bg-primary/10 text-primary", seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
          onClick={isPlaying ? pause : continuePlayback}
          aria-label={isPlaying ? "暂停语音" : "继续播放语音"}
        >
          {isPlaying ? <Pause className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}
          {seniorMode && <span>{isPlaying ? "暂停" : "继续"}</span>}
        </Button>
        <Button
          variant="ghost"
          size={seniorMode ? "default" : "icon-sm"}
          className={cn(seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
          onClick={stop}
          aria-label="停止语音"
        >
          <Square className="size-4" aria-hidden />
          {seniorMode && <span>停止</span>}
        </Button>
        <div
          className={cn("h-1.5 w-16 overflow-hidden rounded-full bg-muted", seniorMode && "w-20")}
          role="progressbar"
          aria-label="语音播放进度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
        >
          <div
            className="h-full origin-left rounded-full bg-primary transition-transform duration-150 motion-reduce:transition-none"
            style={{ transform: `scaleX(${Math.min(1, Math.max(0, progress))})` }}
          />
        </div>
      </div>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon-sm"}
            className={cn(seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
            onClick={start}
            aria-label="语音朗读"
          />
        }
      >
        <Volume2 className={seniorMode ? "size-5" : "size-4"} aria-hidden />
        {seniorMode && <span>朗读</span>}
      </TooltipTrigger>
      <TooltipContent>语音朗读</TooltipContent>
    </Tooltip>
  );
}
