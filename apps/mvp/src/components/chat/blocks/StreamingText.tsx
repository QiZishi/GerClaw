"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface StreamingTextProps {
  /** 完整目标文本（流式追加至该文本） */
  content: string;
  /** 是否处于流式状态 */
  streaming?: boolean;
  className?: string;
}

/**
 * 流式文本：逐字追加 + 末尾闪烁光标
 * 仅在 streaming=true 时执行逐字追加；非流式时直接渲染完整文本。
 */
export function StreamingText({
  content,
  streaming = false,
  className,
}: StreamingTextProps) {
  const [displayed, setDisplayed] = useState<string>("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!streaming) return;
    if (timerRef.current) clearInterval(timerRef.current);
    // 流式：从当前已显示长度逐步追加
    let idx = displayed.length;
    if (idx >= content.length) return;
    timerRef.current = setInterval(() => {
      idx += 1;
      if (idx >= content.length) {
        setDisplayed(content);
        if (timerRef.current) clearInterval(timerRef.current);
      } else {
        setDisplayed(content.slice(0, idx));
      }
    }, 30);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, streaming]);

  // 非流式时直接渲染完整内容，避免在 effect 中同步 setState
  if (!streaming) {
    return <span className={cn("whitespace-pre-wrap", className)}>{content}</span>;
  }

  return (
    <span className={cn("whitespace-pre-wrap", className)}>
      {displayed}
      <span className="typing-cursor" aria-hidden />
    </span>
  );
}
