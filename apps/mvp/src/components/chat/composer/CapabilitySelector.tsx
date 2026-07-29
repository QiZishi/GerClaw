"use client";

import { useMemo, useState } from "react";
import { Blocks, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import {
  listCapabilities,
} from "@/services/gerclaw/capabilities";
import type { CapabilityManifest } from "@/services/gerclaw/capabilities-contract";

interface CapabilitySelectorProps {
  selectedIds: string[];
  seniorMode: boolean;
  disabled: boolean;
  onChange: (ids: string[]) => void;
}

export function CapabilitySelector({
  selectedIds,
  seniorMode,
  disabled,
  onChange,
}: CapabilitySelectorProps) {
  const [open, setOpen] = useState(false);
  const [capabilities, setCapabilities] = useState<CapabilityManifest[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const manualCapabilities = useMemo(
    () => capabilities.filter((item) => item.manual_selection),
    [capabilities],
  );

  const load = async () => {
    setStatus("loading");
    try {
      setCapabilities(await listCapabilities());
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen && (status === "idle" || status === "error")) void load();
  };

  const toggle = (capabilityId: string) => {
    onChange(
      selectedIds.includes(capabilityId)
        ? selectedIds.filter((id) => id !== capabilityId)
        : [...selectedIds, capabilityId],
    );
  };

  return (
    <DropdownMenu open={open} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon"}
            className={cn("btn-icon shrink-0", seniorMode && "order-4 h-12 gap-2 px-3 text-base")}
            aria-label="选择专业能力"
            aria-expanded={open}
            disabled={disabled}
          />
        }
      >
        <Blocks className="size-4" aria-hidden />
        {seniorMode && <span>能力{selectedIds.length > 0 ? ` ${selectedIds.length}` : ""}</span>}
        {!seniorMode && selectedIds.length > 0 && (
          <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-primary px-1 text-[10px] leading-4 text-primary-foreground">
            {selectedIds.length}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="top"
        align="start"
        className="w-[min(24rem,calc(100vw-2rem))] p-2"
      >
        <div className="px-2 pb-2">
          <p className={cn("font-semibold", seniorMode ? "text-lg" : "text-sm")}>本次任务使用的专业能力</p>
          <p className={cn("mt-1 text-muted-foreground", seniorMode ? "text-base leading-7" : "text-xs")}>
            可多选；不选择时，助手仍会按问题自动决定。
          </p>
        </div>
        {status === "loading" && (
          <p className={cn("px-2 py-6 text-center text-muted-foreground", seniorMode && "text-lg")} role="status">
            正在读取可用能力
          </p>
        )}
        {status === "error" && (
          <div className="space-y-2 px-2 py-4 text-center" role="alert">
            <p className={cn("text-destructive", seniorMode && "text-lg")}>专业能力暂时无法读取</p>
            <Button variant="outline" onClick={() => void load()}>重新读取</Button>
          </div>
        )}
        {status === "ready" && manualCapabilities.length === 0 && (
          <p className={cn("px-2 py-6 text-center text-muted-foreground", seniorMode && "text-lg")}>
            当前没有可手动选择的能力
          </p>
        )}
        {manualCapabilities.map((capability) => {
          const selected = selectedIds.includes(capability.capability_id);
          return (
            <button
              key={capability.capability_id}
              type="button"
              className={cn(
                "flex min-h-14 w-full items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                seniorMode && "min-h-16 py-3",
              )}
              aria-pressed={selected}
              onClick={() => toggle(capability.capability_id)}
            >
              <span
                className={cn(
                  "mt-0.5 grid size-5 shrink-0 place-items-center rounded border",
                  selected ? "border-primary bg-primary text-primary-foreground" : "border-border",
                )}
              >
                {selected && <Check className="size-3" aria-hidden />}
              </span>
              <span>
                <span className={cn("block font-medium", seniorMode ? "text-lg" : "text-sm")}>
                  {capability.display_name}
                </span>
                <span className={cn("mt-0.5 block text-muted-foreground", seniorMode ? "text-base leading-7" : "text-xs")}>
                  {capability.risk_level === "high" ? "高风险能力，执行仍受服务端医疗门禁约束" : "由现有受治理服务执行"}
                </span>
              </span>
            </button>
          );
        })}
        {status === "ready" && (
          <div className="mt-2 border-t border-border px-2 pt-2">
            <Button
              type="button"
              className={cn("w-full", seniorMode && "min-h-12 text-lg")}
              onClick={() => setOpen(false)}
            >
              完成选择
            </Button>
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
