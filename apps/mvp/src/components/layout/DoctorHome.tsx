"use client";

import { Stethoscope } from "lucide-react";
import { ChatArea } from "@/components/layout/ChatArea";

export function DoctorHome() {
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background">
      <header className="flex items-center justify-between gap-2 px-4 h-12 border-b border-border bg-background/95 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <Stethoscope className="size-4 text-primary" />
          <span className="text-sm font-medium">医生工作台</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Stethoscope className="size-3.5" />
          <span>GerClaw 辅助诊疗</span>
        </div>
      </header>
      <ChatArea />
    </div>
  );
}
