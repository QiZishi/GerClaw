"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Zap,
  Check,
  HelpCircle,
  LogOut,
  Menu,
  Moon,
  Pin,
  Plus,
  Search,
  Settings,
  Stethoscope,
  Sun,
  Trash2,
  User,
  Users,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { useTheme } from "@/context/ThemeProvider";
import { LAYOUT } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { formatRelativeTime, groupByTime, type SessionGroup } from "@/lib/format";
import type { Session } from "@/types";
import { toast } from "@/components/ui/toast";

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
  const seniorMode = useAppStore((s) => s.seniorMode);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const setRole = useAppStore((s) => s.setRole);
  const setSeniorMode = useAppStore((s) => s.setSeniorMode);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setPanelContent = useAppStore((s) => s.setPanelContent);
  const closeRightPanel = useAppStore((s) => s.closeRightPanel);
  const mainView = useAppStore((s) => s.mainView);
  const setMainView = useAppStore((s) => s.setMainView);
  const { resolvedTheme, toggleTheme } = useTheme();

  const sessions = useChatStore((s) => s.sessions);
  const createSession = useChatStore((s) => s.createSession);
  const renameSession = useChatStore((s) => s.renameSession);
  const removeSession = useChatStore((s) => s.removeSession);
  const togglePinSession = useChatStore((s) => s.togglePinSession);

  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const isPatient = role === "patient";
  const isDoctor = role === "doctor";
  const isVisitor = role === "visitor";

  function getRoleBadgeLabel() {
    switch (role) {
      case "doctor":
        return "医生端";
      case "patient":
        return "患者端";
      case "visitor":
      default:
        return "访客端";
    }
  }

  function getRoleBadgeColor() {
    switch (role) {
      case "doctor":
        return "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300";
      case "patient":
        return "";
      case "visitor":
      default:
        return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
    }
  }

  function getModeLabel() {
    switch (role) {
      case "doctor":
        return "医生模式";
      case "patient":
        return "患者模式";
      case "visitor":
      default:
        return "访客模式";
    }
  }

  const effectiveSessions = sessions;

  // 过滤+分组
  const groupedSessions = useMemo(() => {
    const filtered = effectiveSessions.filter((s) =>
      searchQuery.trim()
        ? s.title.toLowerCase().includes(searchQuery.toLowerCase())
        : true
    );
    const groups: Record<SessionGroup, Session[]> = {
      今天: [],
      昨天: [],
      最近7天: [],
      更早: [],
    };
    for (const s of filtered) {
      const g = groupByTime(s.updatedAt);
      groups[g].push(s);
    }
    // 置顶单独排序
    for (const k of Object.keys(groups) as SessionGroup[]) {
      groups[k].sort((a, b) => {
        if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1;
        return b.updatedAt - a.updatedAt;
      });
    }
    return groups;
  }, [effectiveSessions, searchQuery]);

  const handleNewSession = () => {
    const id = createSession(role);
    setCurrentSession(id);
    setMainView("chat");
    setPanelContent("");
    closeRightPanel();
    onNavigate?.();
  };

  const handleSelectSession = (id: string) => {
    setCurrentSession(id);
    setMainView("chat");
    // 根据会话 panelType 自动展开右侧面板（若该会话有生成结果）
    const session = effectiveSessions.find((s) => s.id === id);
    if (session?.panelType) {
      setRightPanel(session.panelType);
      setPanelContent(session.panelContent ?? "");
    } else {
      setPanelContent("");
      closeRightPanel();
    }
    onNavigate?.();
  };

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

  const handleRoleChange = (nextRole: "visitor" | "patient" | "doctor") => {
    setRole(nextRole);
    onNavigate?.();
  };

  const handleOpenSettings = () => {
    setRightPanel("settings");
    onNavigate?.();
  };

  const handleShowHelp = () => {
    toast.show("帮助中心正在整理中；您可以先选择患者模式或医生模式开始咨询。");
    onNavigate?.();
  };

  const handleExit = () => {
    setRole("visitor");
    setCurrentSession(null);
    closeRightPanel();
    toast.show("已返回访客模式");
    onNavigate?.();
  };

  return (
    <aside
      className="flex h-full flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border"
      style={{ width: onNavigate ? "100%" : LAYOUT.sidebar.expanded }}
    >
      {/* ===== 顶部：标识区 + 折叠按钮 ===== */}
      <div className={cn("flex items-center gap-2 px-3 h-14 shrink-0", seniorMode && "h-16")}>
        <div className="flex items-center justify-center size-8 rounded-lg bg-primary text-primary-foreground shrink-0">
          <Stethoscope className="size-4" />
        </div>
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className={cn("font-bold text-base", seniorMode && "text-lg")}>GerClaw</span>
          <Badge variant="secondary" className={cn("shrink-0", seniorMode && "text-base", getRoleBadgeColor())}>
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

      {/* 第1行：新建对话 */}
      <div className="px-3 pb-2">
        <Button
          variant="default"
          className={cn("w-full justify-start gap-2", seniorMode && "min-h-12 text-lg")}
          onClick={handleNewSession}
        >
          <Plus className="size-4" />
          <span>新建对话</span>
        </Button>
      </div>

      {/* 第2行：技能管理（⚡图标在前，"技能"两字在后） */}
      <div className="px-3 pb-2">
        <Button
          variant={mainView === "skills" ? "secondary" : "ghost"}
          className={cn("w-full justify-start gap-2", seniorMode && "min-h-12 text-lg")}
          onClick={handleToggleSkills}
          aria-label="技能"
        >
          <Zap className="size-4" />
          <span>技能</span>
        </Button>
      </div>

      {/* 第3行：搜索框 */}
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="搜索历史对话"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={cn("pl-8 h-8", seniorMode && "h-12 pl-10 text-lg")}
          />
        </div>
      </div>

      {/* 历史对话列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="px-2 py-1">
          {!mounted ? (
            <div className={cn("px-2 py-4 text-center text-sm text-muted-foreground", seniorMode && "text-lg")}>
              加载中...
            </div>
          ) : effectiveSessions.length === 0 ? (
            <div className="px-3 py-7 text-center">
              <p className={cn("text-sm font-medium", seniorMode && "text-lg")}>还没有对话</p>
              <p className={cn("mt-1 text-xs leading-relaxed text-muted-foreground", seniorMode && "text-base")}>点击“新建对话”，用语音或文字开始健康咨询。</p>
            </div>
          ) : (
            (Object.keys(groupedSessions) as SessionGroup[]).map((group) => {
              const list = groupedSessions[group];
              if (list.length === 0) return null;
              return (
                <div key={group} className="mb-2">
                  <div className={cn("px-2 py-1 text-xs font-medium text-muted-foreground", seniorMode && "text-base")}>
                    {group}
                  </div>
                  {list.map((s) => (
                    <SessionItem
                      key={s.id}
                      session={s}
                      active={currentSessionId === s.id}
                      onSelect={() => handleSelectSession(s.id)}
                      onRename={(title) => renameSession(s.id, title)}
                      onDelete={() => removeSession(s.id)}
                      onTogglePin={() => togglePinSession(s.id)}
                      seniorMode={seniorMode}
                    />
                  ))}
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>

      <Separator className="bg-sidebar-border" />

      {/* ===== 底部：用户菜单（最下方；设置/主题/角色/老年模式均收纳进下拉菜单）===== */}
      <div className="px-3 py-2">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                className={cn(
                  "flex items-center gap-2 w-full rounded-lg hover:bg-sidebar-accent p-1.5 transition-colors",
                  seniorMode && "min-h-14 px-2 py-2 text-lg"
                )}
                aria-label="用户菜单"
              />
            }
          >
            <Avatar size="default" className="shrink-0">
              <AvatarFallback>
                {isDoctor ? (
                  <Stethoscope className="size-4" />
                ) : isPatient ? (
                  <User className="size-4" />
                ) : (
                  <Users className="size-4" />
                )}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0 text-left">
              <div className={cn("text-sm font-medium truncate", seniorMode && "text-lg")}>访客用户</div>
              <div className={cn("text-xs text-muted-foreground truncate", seniorMode && "text-base")}>
                {getModeLabel()}
              </div>
            </div>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className={cn("w-60", seniorMode && "w-72 text-base")}>
            <DropdownMenuGroup>
              <DropdownMenuLabel>访客用户</DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />

            {/* 角色选择 */}
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">选择模式</DropdownMenuLabel>
              <DropdownMenuItem
                className={cn("cursor-pointer gap-2", seniorMode && "min-h-12 text-base", isVisitor && "bg-accent")}
                onClick={() => handleRoleChange("visitor")}
              >
                <Users className="size-4 text-gray-500" />
                <span>访客模式</span>
                {isVisitor && <Check className="size-4 ml-auto" />}
              </DropdownMenuItem>
              <DropdownMenuItem
                className={cn("cursor-pointer gap-2", seniorMode && "min-h-12 text-base", isPatient && "bg-accent")}
                onClick={() => handleRoleChange("patient")}
              >
                <User className="size-4 text-primary" />
                <span>患者模式</span>
                {isPatient && <Check className="size-4 ml-auto" />}
              </DropdownMenuItem>
              <DropdownMenuItem
                className={cn("cursor-pointer gap-2", seniorMode && "min-h-12 text-base", isDoctor && "bg-accent")}
                onClick={() => handleRoleChange("doctor")}
              >
                <Stethoscope className="size-4 text-blue-600" />
                <span>医生模式</span>
                {isDoctor && <Check className="size-4 ml-auto" />}
              </DropdownMenuItem>
            </DropdownMenuGroup>

            <DropdownMenuSeparator />

            {/* 老年模式（仅患者端）*/}
            {isPatient && (
              <div className={cn("flex items-center justify-between px-2 py-1.5 text-sm", seniorMode && "min-h-12 text-base")}>
                <span>老年模式</span>
                <Switch
                  checked={seniorMode}
                  onCheckedChange={(v) => setSeniorMode(v)}
                  aria-label="切换老年模式"
                />
              </div>
            )}

            {/* 主题切换 */}
            <DropdownMenuItem
              onClick={toggleTheme}
              className={cn("flex items-center justify-between cursor-pointer", seniorMode && "min-h-12 text-base")}
            >
              <span className="flex items-center gap-2">
                {resolvedTheme === "dark" ? (
                  <Sun className="size-4" />
                ) : (
                  <Moon className="size-4" />
                )}
                主题
              </span>
              <span className={cn("text-xs text-muted-foreground", seniorMode && "text-base")}>
                {resolvedTheme === "dark" ? "深色" : "浅色"}
              </span>
            </DropdownMenuItem>

            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={handleOpenSettings}>
                <Settings className="size-4" />
                设置
              </DropdownMenuItem>
              <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={handleShowHelp}>
                <HelpCircle className="size-4" />
                帮助
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={handleExit}>
              <LogOut className="size-4" />
              退出
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
}

/** 单个会话项 */
function SessionItem({
  session,
  active,
  onSelect,
  onRename,
  onDelete,
  onTogglePin,
  seniorMode,
}: {
  session: Session;
  active: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
  onTogglePin: () => void;
  seniorMode: boolean;
}) {
  // onRename 当前未接入 UI（重命名弹窗在 Phase 4 接入）
  void onRename;

  return (
    <div
      data-session-item
      className={cn(
        "group relative flex items-center gap-2 rounded-xl px-2 py-2.5 mx-0.5 transition-colors duration-150 ease-out",
        seniorMode && "flex-col items-stretch px-3 py-3",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "hover:bg-sidebar-accent/70"
      )}
    >
      {/* 选中态左侧指示条 */}
      <div
        className={cn(
          "absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-full bg-primary transition-all duration-200 ease-out",
          active ? "opacity-100" : "opacity-0"
        )}
      />
      <button type="button" className={cn("flex-1 min-w-0 ml-1 text-left", seniorMode && "min-h-12")} onClick={onSelect}>
        <div className="flex items-center gap-1">
          {session.pinned && <Pin className="size-3 text-primary shrink-0" />}
          <div className={cn("text-sm font-medium truncate", seniorMode && "text-lg")}>{session.title}</div>
        </div>
        <div className={cn("text-xs text-muted-foreground truncate mt-0.5", seniorMode && "text-base")}>
          {session.lastMessagePreview ?? formatRelativeTime(session.updatedAt)}
        </div>
      </button>
      {/* 操作按钮 */}
      <div className={cn(
        "flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150 ease-out",
        seniorMode && "justify-end gap-2 opacity-100"
      )}>
        <button
          type="button"
          className={cn(
            "p-1.5 rounded-lg hover:bg-background text-muted-foreground hover:text-foreground transition-colors",
            seniorMode && "inline-flex min-h-12 items-center gap-1.5 px-3 text-base"
          )}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin();
          }}
          aria-label={session.pinned ? "取消置顶" : "置顶"}
        >
          <Pin className="size-3.5" />
          {seniorMode && <span>{session.pinned ? "取消置顶" : "置顶"}</span>}
        </button>
        <button
          type="button"
          className={cn(
            "p-1.5 rounded-lg hover:bg-background text-muted-foreground hover:text-destructive transition-colors",
            seniorMode && "inline-flex min-h-12 items-center gap-1.5 px-3 text-base"
          )}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          aria-label="删除"
        >
          <Trash2 className="size-3.5" />
          {seniorMode && <span>删除</span>}
        </button>
      </div>
    </div>
  );
}
