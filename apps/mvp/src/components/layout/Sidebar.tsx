"use client";

import { useEffect, useState } from "react";
import {
  Zap,
  Menu,
  Plus,
  Stethoscope,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAppStore } from "@/stores/appStore";
import { useTheme } from "@/context/ThemeProvider";
import { cn } from "@/lib/utils";
import { SidebarSessionHistory } from "@/components/layout/sidebar/SidebarSessionHistory";
import { SidebarSessionDialogs } from "@/components/layout/sidebar/SidebarSessionDialogs";
import { SidebarAccountMenu } from "@/components/layout/sidebar/SidebarAccountMenu";
import { SidebarAccountDialogs } from "@/components/layout/sidebar/SidebarAccountDialogs";
import { useSidebarSessionController } from "@/components/layout/sidebar/useSidebarSessionController";
import { useSidebarAccountController } from "@/components/layout/sidebar/useSidebarAccountController";

interface SidebarProps {
  /** 移动端用：关闭抽屉的回调 */
  onNavigate?: () => void;
}

/**
 * §3.2 左侧边栏
 * 展开 272px / 折叠 64px
 * 顶部：标识 / 折叠按钮 / 新建对话 / 搜索 / 历史列表 / 技能入口
 * 底部：用户信息 / 模式切换 / 老年模式 / 主题
 */
export function Sidebar({ onNavigate }: SidebarProps) {
  const [mounted, setMounted] = useState(false);

  const role = useAppStore((s) => s.role);
  const isGuest = useAppStore((s) => s.isGuest);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const setSeniorMode = useAppStore((s) => s.setSeniorMode);
  const mainView = useAppStore((s) => s.mainView);
  const setMainView = useAppStore((s) => s.setMainView);
  const { resolvedTheme, toggleTheme } = useTheme();

  const {
    sessions,
    currentSessionId,
    patientHistoryOpen,
    setPatientHistoryOpen,
    renameTarget,
    renameTitle,
    setRenameTitle,
    setRenameTarget,
    deleteTarget,
    setDeleteTarget,
    deletingSession,
    pendingRole,
    setPendingRole,
    handleNewSession,
    handleSelectSession,
    confirmRoleChange,
    openRename,
    confirmRename,
    confirmDelete,
    togglePinSession,
  } = useSidebarSessionController(onNavigate);
  const {
    account,
    menuActions,
    dialogs: accountDialogs,
  } = useSidebarAccountController({
    mounted,
    onNavigate,
    openHistory: () => setPatientHistoryOpen(true),
    setSeniorMode,
    toggleTheme,
  });

  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const isPatient = role === "patient";
  const isDoctor = role === "doctor";

  function getRoleBadgeLabel() {
    switch (role) {
      case "doctor":
        return "医生端";
      case "patient":
        return "患者端";
      default:
        return "患者端";
    }
  }

  function getRoleBadgeColor() {
    switch (role) {
      case "doctor":
        return "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300";
      case "patient":
        return "";
      default:
        return "";
    }
  }

  const effectiveSessions = sessions;

  const handleToggleSkills = () => {
    // 对齐 Trae Work：技能管理切换到中间栏显示
    setMainView(mainView === "skills" ? "chat" : "skills");
    onNavigate?.();
  };

  const handleCollapse = () => {
    if (onNavigate) {
      onNavigate();
      return;
    }
    toggleSidebar();
  };

  return (
    <aside
      className="flex h-full flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border"
      style={{ width: "100%" }}
    >
      {/* ===== 顶部：标识区 + 折叠按钮 ===== */}
      <div
        className={cn(
          "flex items-center gap-2 px-3 h-14 shrink-0",
          seniorMode && "h-auto min-h-20 items-start py-2",
        )}
      >
        <div className="flex items-center justify-center size-8 rounded-lg bg-primary text-primary-foreground shrink-0">
          <Stethoscope className="size-4" />
        </div>
        <div
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2",
            seniorMode && "flex-col items-start gap-0.5 pt-0.5",
          )}
        >
          <span className={cn("font-bold text-base", seniorMode && "text-lg")}>GerClaw</span>
          <Badge
            data-sidebar-role-badge
            variant="secondary"
            className={cn("shrink-0", getRoleBadgeColor())}
          >
            {getRoleBadgeLabel()}
          </Badge>
        </div>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size={seniorMode ? "default" : "icon-sm"}
                className={cn("btn-icon shrink-0", seniorMode && "min-h-12 gap-1 px-2 text-base")}
                onClick={handleCollapse}
                aria-label={onNavigate ? "关闭菜单" : "折叠侧边栏"}
              />
            }
          >
            <Menu className="size-4" />
            {seniorMode && <span>{onNavigate ? "关闭" : "收起"}</span>}
          </TooltipTrigger>
          <TooltipContent>{onNavigate ? "关闭菜单" : "折叠"}</TooltipContent>
        </Tooltip>
      </div>

      {/* The two roles share the same visual hierarchy; only their task language differs. */}
      <div className="px-3 pb-2">
        <Button
          variant="default"
          className={cn("w-full justify-start gap-2", seniorMode && "min-h-12 text-lg")}
          onClick={handleNewSession}
        >
          <Plus className="size-4" />
          <span>{isDoctor ? "新建病例会话" : "开始咨询"}</span>
        </Button>
      </div>

      {/* 技能管理仅对已登录账户开放；游客仅使用患者服务。 */}
      {!isGuest && <div className="px-3 pb-2">
        <Button
          variant={mainView === "skills" ? "secondary" : "ghost"}
          className={cn("w-full justify-start gap-2", seniorMode && "min-h-12 text-lg")}
          onClick={handleToggleSkills}
          aria-label="技能"
        >
          <Zap className="size-4" />
          <span>技能</span>
        </Button>
      </div>}

      <SidebarSessionHistory
        sessions={effectiveSessions}
        currentSessionId={currentSessionId}
        mounted={mounted}
        seniorMode={seniorMode}
        isDoctor={isDoctor}
        isPatient={isPatient}
        patientHistoryOpen={patientHistoryOpen}
        onSelect={handleSelectSession}
        onRename={openRename}
        onDelete={setDeleteTarget}
        onTogglePin={togglePinSession}
      />
      <Separator className="bg-sidebar-border" />

      <SidebarAccountMenu
        account={account}
        role={role}
        isGuest={isGuest}
        seniorMode={seniorMode}
        resolvedTheme={resolvedTheme}
        sessionCount={effectiveSessions.length}
        actions={menuActions}
      />
      <SidebarSessionDialogs
        seniorMode={seniorMode}
        isDoctor={isDoctor}
        renameTarget={renameTarget}
        renameTitle={renameTitle}
        deleteTarget={deleteTarget}
        deletingSession={deletingSession}
        pendingRole={pendingRole}
        onRenameTitleChange={setRenameTitle}
        onCloseRename={() => setRenameTarget(null)}
        onConfirmRename={confirmRename}
        onCloseDelete={() => setDeleteTarget(null)}
        onConfirmDelete={() => void confirmDelete()}
        onCloseRoleChange={() => setPendingRole(null)}
        onConfirmRoleChange={confirmRoleChange}
      />
      <SidebarAccountDialogs
        account={account}
        seniorMode={seniorMode}
        {...accountDialogs}
      />
    </aside>
  );
}
