"use client";

import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatActionType } from "@/types";

interface ChatWorkspaceHeaderProps {
  mainView: "chat" | "skills";
  chatAction: ChatActionType;
  seniorMode: boolean;
  sidebarCollapsed: boolean;
  currentSessionTitle: string;
  showConversationHeader: boolean;
  actionTitle?: string;
  onReturnToChat: () => void;
  onExitAction: () => void;
}

export function ChatWorkspaceHeader({
  mainView,
  chatAction,
  seniorMode,
  sidebarCollapsed,
  currentSessionTitle,
  showConversationHeader,
  actionTitle,
  onReturnToChat,
  onExitAction,
}: ChatWorkspaceHeaderProps) {
  if (mainView === "skills") {
    return (
      <header
        className={cn(
          "sticky top-0 z-10 flex min-h-12 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur",
          seniorMode && "py-2",
        )}
        style={sidebarCollapsed ? { paddingLeft: "112px" } : undefined}
      >
        <Button
          variant="ghost"
          size={seniorMode ? "default" : "icon-sm"}
          className={cn(
            "btn-icon shrink-0",
            seniorMode && "h-12 min-w-32 gap-2 px-4 text-lg",
          )}
          onClick={onReturnToChat}
          aria-label="返回对话"
        >
          <ArrowLeft className={cn("size-4", seniorMode && "size-5")} />
          {seniorMode && <span>返回对话</span>}
        </Button>
        <span className={cn("font-medium", seniorMode && "text-lg")}>
          技能管理
        </span>
      </header>
    );
  }

  if (!showConversationHeader) return null;
  return (
    <header
      className={cn(
        "sticky top-0 z-10 flex h-12 items-center border-b border-border bg-background/95 px-4 backdrop-blur",
        chatAction !== "none"
          ? "justify-end sm:justify-between"
          : "justify-between",
      )}
      style={sidebarCollapsed ? { paddingLeft: "112px" } : undefined}
    >
      {chatAction !== "none" ? (
        <>
          <span className="hidden font-medium sm:block">{actionTitle}</span>
          <Button
            variant="ghost"
            onClick={onExitAction}
            className={cn(
              "min-h-10 px-3 text-sm text-muted-foreground hover:text-foreground",
              seniorMode && "min-h-12 text-lg",
            )}
          >
            {chatAction === "chronic-care" || chatAction === "risk-alerts"
              ? "返回咨询"
              : "退出"}
          </Button>
        </>
      ) : (
        <span className="truncate font-medium" title={currentSessionTitle}>
          {currentSessionTitle || "新对话"}
        </span>
      )}
    </header>
  );
}
