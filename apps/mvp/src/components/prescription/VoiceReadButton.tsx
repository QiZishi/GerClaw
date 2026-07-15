"use client";

import { Pause, Play, Square, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";

interface VoiceReadButtonProps {
  text?: string;
  className?: string;
}

export function VoiceReadButton({ text, className }: VoiceReadButtonProps) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const { isPlaying, isPaused, isLoading, play, pause, resume, stop } = useAudioPlayer();
  const reportError = () => toast.show("语音播放失败，请稍后重试");

  if (isLoading) {
    return (
      <Button
        variant="ghost"
        className={cn("gap-1.5", seniorMode && "min-h-12 px-3 text-base", className)}
        onClick={stop}
        aria-busy="true"
      >
        <Volume2 className="size-4" />
        正在准备，点击取消
      </Button>
    );
  }

  if (isPlaying || isPaused) {
    return (
      <div className={cn("inline-flex items-center gap-1", className)} role="group" aria-label="处方语音播放控制">
        <Button
          variant="ghost"
          size={seniorMode ? "default" : "icon-sm"}
          className={cn(seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
          onClick={isPlaying ? pause : () => void resume().catch(reportError)}
          aria-label={isPlaying ? "暂停朗读" : "继续朗读"}
        >
          {isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />}
          {seniorMode && <span>{isPlaying ? "暂停" : "继续"}</span>}
        </Button>
        <Button
          variant="ghost"
          size={seniorMode ? "default" : "icon-sm"}
          className={cn(seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
          onClick={stop}
          aria-label="停止朗读"
        >
          <Square className="size-4" />
          {seniorMode && <span>停止</span>}
        </Button>
      </div>
    );
  }

  return (
    <Button
      variant="ghost"
      size={seniorMode ? "default" : "icon-sm"}
      className={cn(seniorMode && "min-h-12 gap-1.5 px-3 text-base", className)}
      onClick={() => text && void play(text).catch(reportError)}
      aria-label="朗读处方"
      disabled={!text}
    >
      <Volume2 className="size-4" />
      {seniorMode && <span>朗读</span>}
    </Button>
  );
}
