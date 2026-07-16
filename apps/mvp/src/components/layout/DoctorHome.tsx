"use client";

import { Stethoscope } from "lucide-react";
import { ChatArea } from "@/components/layout/ChatArea";

export function DoctorHome() {
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background">
      <header className="sticky top-0 z-10 flex h-12 items-center justify-between gap-2 border-b border-border bg-background/95 pl-32 pr-4 backdrop-blur md:px-4">
        <div className="flex items-center gap-2">
          <Stethoscope className="size-4 text-primary" />
          <span className="text-sm font-medium">医生工作台</span>
        </div>
        <div className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
          <Stethoscope className="size-3.5" />
          <span>GerClaw 辅助诊疗</span>
        </div>
      </header>
      <ChatArea />
    </div>
  );
}
