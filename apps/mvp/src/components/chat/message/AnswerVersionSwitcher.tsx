"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import {
  adjacentAnswerVersion,
  orderedAnswerVersions,
} from "@/components/chat/message/answer-version";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import {
  readAnswerVersions,
  selectAnswerVersion,
} from "@/services/gerclaw/runs";
import type { AnswerVersion } from "@/services/gerclaw/run-contract";
import { cn } from "@/lib/utils";

interface AnswerVersionSwitcherProps {
  runId?: string;
  currentVersionId?: string;
  currentVersion?: number;
  seniorMode: boolean;
  onSelected?: (version: AnswerVersion) => Promise<void>;
}

export function AnswerVersionSwitcher({
  runId,
  currentVersionId,
  currentVersion,
  seniorMode,
  onSelected,
}: AnswerVersionSwitcherProps) {
  const [versions, setVersions] = useState<AnswerVersion[]>([]);
  const [selectedId, setSelectedId] = useState(currentVersionId ?? "");
  const [selecting, setSelecting] = useState(false);

  useEffect(() => {
    if (!runId || !currentVersionId) return;
    let active = true;
    void readAnswerVersions(runId)
      .then((result) => {
        if (!active) return;
        setVersions(orderedAnswerVersions(result.versions));
        setSelectedId(result.versions.find((version) => version.is_current)?.id ?? currentVersionId);
      })
      .catch(() => {
        if (active) setVersions([]);
      });
    return () => {
      active = false;
    };
  }, [currentVersionId, runId]);

  if (!runId || !currentVersionId || versions.length < 2) return null;
  const selected = versions.find((version) => version.id === selectedId);
  const previous = adjacentAnswerVersion(versions, selectedId, -1);
  const next = adjacentAnswerVersion(versions, selectedId, 1);

  const choose = async (target: AnswerVersion | null) => {
    if (!target || selecting) return;
    setSelecting(true);
    try {
      const result = await selectAnswerVersion(runId, target.id, selectedId);
      setSelectedId(result.id);
      await onSelected?.(result);
      toast.show(`已切换到回答版本 ${result.version}`);
    } catch {
      toast.show("回答版本切换失败，请刷新后重试");
    } finally {
      setSelecting(false);
    }
  };

  return (
    <div className={cn("flex items-center gap-1 text-muted-foreground", seniorMode && "text-base")} role="group" aria-label="回答版本">
      <Button
        variant="ghost"
        size={seniorMode ? "default" : "icon-sm"}
        className={cn(seniorMode && "min-h-12 gap-1 px-3")}
        disabled={!previous || selecting}
        onClick={() => void choose(previous)}
        aria-label="查看上一个回答版本"
      >
        <ChevronLeft className="size-4" aria-hidden />
        {seniorMode && <span>上一版</span>}
      </Button>
      <span className="whitespace-nowrap tabular-nums" aria-live="polite">
        版本 {selected?.version ?? currentVersion ?? 1}/{versions.length}
      </span>
      <Button
        variant="ghost"
        size={seniorMode ? "default" : "icon-sm"}
        className={cn(seniorMode && "min-h-12 gap-1 px-3")}
        disabled={!next || selecting}
        onClick={() => void choose(next)}
        aria-label="查看下一个回答版本"
      >
        {seniorMode && <span>下一版</span>}
        <ChevronRight className="size-4" aria-hidden />
      </Button>
    </div>
  );
}
