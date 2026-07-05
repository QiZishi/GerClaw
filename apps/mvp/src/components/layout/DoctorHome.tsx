"use client";

import { useState } from "react";
import { Activity, ChevronLeft, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { PatientList } from "@/components/prescription/doctor/PatientList";
import { ChatArea } from "@/components/layout/ChatArea";
import type { MockPatient } from "@/data/mock/patients";

/**
 * §3.2.2 医生端主视图
 * - 无 currentSessionId 时：显示 PatientList（医生工作台）
 * - 选中患者后：创建会话并进入 ChatArea（复用既有聊天 UI）
 * - 通过外层 sticky header 提供返回入口与患者上下文标识
 */
export function DoctorHome() {
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const createSession = useChatStore((s) => s.createSession);
  const [selectedPatient, setSelectedPatient] = useState<MockPatient | null>(
    null
  );

  const handleSelectPatient = (p: MockPatient) => {
    setSelectedPatient(p);
    const id = createSession("doctor");
    setCurrentSession(id);
    // 选中患者后默认展开健康画像，便于医生查看上下文
    setRightPanel("health-profile");
  };

  const handleBackToList = () => {
    setCurrentSession(null);
    setSelectedPatient(null);
    setRightPanel(null, false);
  };

  // 已有会话：进入医生端工作台（复用 ChatArea，顶部追加返回按钮）
  if (currentSessionId) {
    return (
      <div className="flex-1 flex flex-col min-w-0 bg-background">
        <header className="sticky top-0 z-20 flex items-center gap-2 px-3 h-12 border-b border-border bg-background/95 backdrop-blur">
          <Button
            variant="ghost"
            size="icon-sm"
            className="btn-icon shrink-0"
            onClick={handleBackToList}
            aria-label="返回患者列表"
          >
            <ChevronLeft className="size-4" />
          </Button>
          {selectedPatient && (
            <div className="flex items-center gap-2 min-w-0">
              <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                {selectedPatient.name.slice(0, 1)}
              </div>
              <span className="text-sm font-medium truncate">
                {selectedPatient.name}
              </span>
              <span className="text-xs text-muted-foreground truncate hidden sm:inline">
                {selectedPatient.gender} · {selectedPatient.age} 岁 ·{" "}
                {selectedPatient.chiefComplaint}
              </span>
            </div>
          )}
        </header>
        <ChatArea />
      </div>
    );
  }

  // 无会话：显示患者列表 + 工作台标识
  return (
    <main className="flex-1 flex flex-col min-w-0 bg-background">
      <header className="flex items-center justify-between gap-2 px-4 h-12 border-b border-border">
        <div className="flex items-center gap-2">
          <Stethoscope className="size-4 text-primary" />
          <span className="text-sm font-medium">医生工作台</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Activity className="size-3.5" />
          <span>GerClaw 辅助诊疗</span>
        </div>
      </header>
      <div className="flex-1 min-h-0">
        <PatientList
          selectedPatientId={selectedPatient?.id ?? null}
          onSelectPatient={handleSelectPatient}
        />
      </div>
    </main>
  );
}
