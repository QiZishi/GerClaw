"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Volume2, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type PlayState = "idle" | "loading" | "playing";

interface VoiceReadButtonProps {
  /** 朗读文本 */
  text?: string;
  className?: string;
  /** mock 载入时长，默认 1000ms */
  loadingMs?: number;
}

/**
 * §语音交互 — 语音朗读按钮
 * idle → loading (1s) → playing → idle（再次点击停止）
 * mock 阶段不调用真实 TTS
 */
export function VoiceReadButton({
  text,
  className,
  loadingMs = 1000,
}: VoiceReadButtonProps) {
  const [state, setState] = useState<PlayState>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleClick = () => {
    if (state === "idle") {
      setState("loading");
      timerRef.current = setTimeout(() => {
        setState("playing");
      }, loadingMs);
    } else if (state === "playing") {
      setState("idle");
      if (timerRef.current) clearTimeout(timerRef.current);
    } else if (state === "loading") {
      setState("idle");
      if (timerRef.current) clearTimeout(timerRef.current);
    }
  };

  const label =
    state === "idle"
      ? "朗读"
      : state === "loading"
        ? "加载中"
        : "停止";

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className={cn("btn-icon", className)}
            onClick={handleClick}
            aria-label={label}
            aria-pressed={state === "playing"}
          />
        }
      >
        {state === "loading" ? (
          <Loader2 className="size-4 animate-spin" />
        ) : state === "playing" ? (
          <VolumeX className="size-4 text-primary" />
        ) : (
          <Volume2 className="size-4" />
        )}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
      {text && <span className="sr-only">{text.slice(0, 200)}</span>}
    </Tooltip>
  );
}
