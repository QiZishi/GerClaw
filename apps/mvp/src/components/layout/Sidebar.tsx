"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeftRight,
  Copy,
  Zap,
  HelpCircle,
  History,
  LogOut,
  Menu,
  Moon,
  Pencil,
  Pin,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Stethoscope,
  Sun,
  Trash2,
  User,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { AccountDialog } from "@/components/account/AccountDialog";
import { AccountDeactivationDialog } from "@/components/account/AccountDeactivationDialog";
import { PrescriptionReviewAccessDialog } from "@/components/consent/PrescriptionReviewAccessDialog";
import { DoctorCgaWorkspaceDialog } from "@/components/consent/DoctorCgaWorkspaceDialog";
import { DoctorPrescriptionReviewDialog } from "@/components/consent/DoctorPrescriptionReviewDialog";
import {
  getAccountIdentity,
  exitGuestSession,
  logoutAccount,
  switchAdministratorView,
  type AccountIdentity,
} from "@/services/account";
import { deleteBackendSession } from "@/services/gerclaw/skills";

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
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const setChatAction = useAppStore((s) => s.setChatAction);
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
  const clearAllData = useChatStore((s) => s.clearAllData);

  const [searchQuery, setSearchQuery] = useState("");
  const [patientHistoryOpen, setPatientHistoryOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Session | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [deletingSession, setDeletingSession] = useState(false);
  const [pendingRole, setPendingRole] = useState<"patient" | "doctor" | null>(null);
  const [account, setAccount] = useState<AccountIdentity | null>(null);
  const [accountDialogOpen, setAccountDialogOpen] = useState(false);
  const [accountDeactivationOpen, setAccountDeactivationOpen] = useState(false);
  const [prescriptionReviewAccessOpen, setPrescriptionReviewAccessOpen] = useState(false);
  const [doctorPrescriptionReviewOpen, setDoctorPrescriptionReviewOpen] = useState(false);
  const [doctorCgaWorkspaceOpen, setDoctorCgaWorkspaceOpen] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    void getAccountIdentity().then((identity) => {
      if (!identity) return;
      setAccount(identity);
      setRole(identity.role);
    });
  }, [mounted, setRole]);

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

  function getModeLabel() {
    switch (role) {
      case "doctor":
        return "医生模式";
      case "patient":
        return "患者模式";
      default:
        return "患者模式";
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
      // A generated prescription is a conversation, not merely a detached
      // preview. Restore its chat-native status and clinician feedback while
      // keeping the persisted report open alongside it.
      if (session.panelType === "prescription") setChatAction("prescription");
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

  const confirmRoleChange = () => {
    if (!pendingRole) return;
    setRole(pendingRole);
    setPendingRole(null);
    onNavigate?.();
  };

  const openRename = (session: Session) => {
    setRenameTarget(session);
    setRenameTitle(session.title);
  };

  const confirmRename = () => {
    const title = renameTitle.trim();
    if (!renameTarget || !title) return;
    renameSession(renameTarget.id, title);
    setRenameTarget(null);
    toast.show(isDoctor ? "病例会话名称已更新" : "对话名称已更新");
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletingSession(true);
    try {
      await deleteBackendSession(deleteTarget.id);
      const wasCurrentSession = deleteTarget.id === currentSessionId;
      removeSession(deleteTarget.id);
      if (wasCurrentSession) {
        setCurrentSession(null);
        setMainView("chat");
        setPanelContent("");
        closeRightPanel();
      }
      setDeleteTarget(null);
      toast.show(isDoctor ? "病例会话已删除" : "对话已删除");
      onNavigate?.();
    } catch {
      toast.show(
        isDoctor
          ? "暂时无法删除病例会话，请稍后重试。"
          : "暂时无法删除对话，请稍后重试。",
      );
    } finally {
      setDeletingSession(false);
    }
  };

  const roleLabel = (value: "visitor" | "patient" | "doctor") => {
    if (value === "patient") return "患者模式";
    if (value === "doctor") return "医生模式";
    return "患者模式";
  };

  const handleOpenSettings = () => {
    setRightPanel("settings");
    onNavigate?.();
  };

  const handleShowHelp = () => {
    toast.show("帮助中心正在整理中；您可以先选择患者模式或医生模式开始咨询。");
    onNavigate?.();
  };

  const handleExit = async () => {
    if (account) {
      try {
        await logoutAccount();
      } catch {
        toast.show("暂时无法安全退出账户，请稍后重试。");
        return;
      }
      setAccount(null);
    } else {
      try {
        await exitGuestSession();
      } catch {
        toast.show("暂时无法结束本次使用，请稍后重试。");
        return;
      }
    }
    clearAllData();
    window.location.assign("/");
    setCurrentSession(null);
    closeRightPanel();
    toast.show("已返回登录页");
    onNavigate?.();
  };

  const handleAdminWorkspace = async (targetRole: "patient" | "doctor") => {
    try {
      await switchAdministratorView(targetRole);
      clearAllData();
      window.location.assign("/");
    } catch {
      toast.show("工作区切换未完成，请稍后重试。");
    }
  };

  const openAdminConsole = () => {
    window.location.assign("/?workspace=admin");
  };

  const isAdministrator = account?.account_role === "admin";

  async function copyReviewCode(kind: "医生" | "患者") {
    if (!account || !navigator.clipboard) {
      toast.show(`暂时无法复制${kind}代码`);
      return;
    }
    try {
      await navigator.clipboard.writeText(account.actor_id);
      toast.show(`${kind}代码已复制`);
    } catch {
      toast.show(`暂时无法复制${kind}代码`);
    }
  }

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

      {/* History stays available without occupying the patient's primary action area. */}
      {(!isPatient || patientHistoryOpen) && <div className="px-3 pb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
          <Input
            placeholder={isDoctor ? "搜索病例会话" : "搜索对话记录"}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={cn("pl-8 h-8", seniorMode && "h-12 pl-10 text-lg")}
          />
        </div>
      </div>}

      {(!isPatient || patientHistoryOpen) && <ScrollArea className="flex-1 min-h-0">
        <div className="px-2 py-1">
          {!mounted ? (
            <div className={cn("px-2 py-4 text-center text-sm text-muted-foreground", seniorMode && "text-lg")}>
              加载中...
            </div>
          ) : effectiveSessions.length === 0 ? (
            <div className="px-3 py-7 text-center">
              <p className={cn("text-sm font-medium", seniorMode && "text-lg")}>{isDoctor ? "还没有病例会话" : "还没有对话记录"}</p>
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
                      onRename={() => openRename(s)}
                      onDelete={() => setDeleteTarget(s)}
                      onTogglePin={() => togglePinSession(s.id)}
                      seniorMode={seniorMode}
                    />
                  ))}
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>}
      {isPatient && !patientHistoryOpen && <div className="flex-1" />}

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
                ) : <User className="size-4" />}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0 text-left">
              <div className={cn("text-sm font-medium truncate", seniorMode && "text-lg")}>{account ? "已登录账户" : isGuest ? "本次使用" : "未登录"}</div>
              <div className={cn("text-xs text-muted-foreground truncate", seniorMode && "text-base")}>
                {getModeLabel()}
              </div>
            </div>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className={cn("w-60", seniorMode && "w-72 text-base")}>
            <DropdownMenuGroup>
              <DropdownMenuLabel>{account ? "账户身份由服务端验证" : "本次使用"}</DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />

            {!account && <>
              <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => setAccountDialogOpen(true)}>
                <User className="size-4" />
                登录或创建账户
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>}

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
              {isPatient && effectiveSessions.length > 0 && (
                <DropdownMenuItem
                  className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")}
                  onClick={() => setPatientHistoryOpen(true)}
                >
                  <History className="size-4" />
                  对话记录
                </DropdownMenuItem>
              )}
              <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={handleOpenSettings}>
                <Settings className="size-4" />
                设置
              </DropdownMenuItem>
              <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={handleShowHelp}>
                <HelpCircle className="size-4" />
                帮助
              </DropdownMenuItem>
              {account?.account_role === "patient" && (
                <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => setPrescriptionReviewAccessOpen(true)}>
                  <ShieldCheck className="size-4" />
                  医生资料授权
                </DropdownMenuItem>
              )}
              {account?.account_role === "patient" && (
                <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => void copyReviewCode("患者")}>
                  <Copy className="size-4" />
                  复制我的患者代码
                </DropdownMenuItem>
              )}
              {account?.account_role === "doctor" && (
                <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => setDoctorPrescriptionReviewOpen(true)}>
                  <ShieldCheck className="size-4" />
                  五大处方草案复核
                </DropdownMenuItem>
              )}
              {account?.account_role === "doctor" && (
                <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => setDoctorCgaWorkspaceOpen(true)}>
                  <Stethoscope className="size-4" />
                  CGA 报告工作区
                </DropdownMenuItem>
              )}
              {account?.account_role === "doctor" && (
                <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => void copyReviewCode("医生")}>
                  <Copy className="size-4" />
                  复制我的复核代码
                </DropdownMenuItem>
              )}
            </DropdownMenuGroup>
            {isAdministrator && <>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={openAdminConsole}>
                  <ShieldCheck className="size-4" />
                  管理控制台
                </DropdownMenuItem>
                {role !== "patient" && <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => void handleAdminWorkspace("patient")}>
                  <ArrowLeftRight className="size-4" />
                  切换到患者端
                </DropdownMenuItem>}
                {role !== "doctor" && <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => void handleAdminWorkspace("doctor")}>
                  <ArrowLeftRight className="size-4" />
                  切换到医生端
                </DropdownMenuItem>}
              </DropdownMenuGroup>
            </>}
            <DropdownMenuSeparator />
            {account && <>
              <DropdownMenuItem className={cn("cursor-pointer text-destructive focus:text-destructive", seniorMode && "min-h-12 text-base")} onClick={() => setAccountDeactivationOpen(true)}>
                <Trash2 className="size-4" />
                停用账户
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>}
            <DropdownMenuItem className={cn("cursor-pointer", seniorMode && "min-h-12 text-base")} onClick={() => void handleExit()}>
              <LogOut className="size-4" />
              {account ? "退出账户" : "结束本次使用"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Dialog
        open={renameTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRenameTarget(null);
        }}
      >
        <DialogContent showCloseButton={!seniorMode} className={cn("sm:max-w-md", seniorMode && "p-5")}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              confirmRename();
            }}
          >
            <DialogHeader>
              <DialogTitle className={cn(seniorMode && "text-2xl")}>{isDoctor ? "重命名病例会话" : "重命名对话"}</DialogTitle>
              <DialogDescription className={cn(seniorMode && "text-lg leading-8")}>
                {isDoctor ? "使用便于识别的名称，方便后续继续病例工作。" : "使用容易识别的名称，方便下次继续咨询。"}
              </DialogDescription>
            </DialogHeader>
            <div className="mt-5">
              <Label htmlFor="session-title" className={cn(seniorMode && "text-lg")}>{isDoctor ? "病例会话名称" : "对话名称"}</Label>
              <Input
                id="session-title"
                autoFocus
                value={renameTitle}
                maxLength={80}
                onChange={(event) => setRenameTitle(event.target.value)}
                className={cn("mt-2", seniorMode && "h-12 text-lg")}
              />
            </div>
            <DialogFooter className={cn("mt-5", seniorMode && "flex-row justify-end gap-3 p-5")}>
              <Button type="button" variant="outline" className={cn(seniorMode && "min-h-12 text-lg")} onClick={() => setRenameTarget(null)}>
                取消
              </Button>
              <Button type="submit" className={cn(seniorMode && "min-h-12 text-lg")} disabled={!renameTitle.trim()}>
                保存名称
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent showCloseButton={!seniorMode} className={cn("sm:max-w-md", seniorMode && "p-5")}>
          <DialogHeader>
            <DialogTitle className={cn("text-destructive", seniorMode && "text-2xl")}>{isDoctor ? "确认删除病例会话" : "确认删除对话"}</DialogTitle>
            <DialogDescription className={cn(seniorMode && "text-lg leading-8")}>
              删除“{deleteTarget?.title}”后，其中的所有内容将无法恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className={cn("mt-5", seniorMode && "flex-row justify-end gap-3 p-5")}>
            <Button variant="outline" className={cn(seniorMode && "min-h-12 text-lg")} onClick={() => setDeleteTarget(null)} disabled={deletingSession}>
              取消
            </Button>
            <Button variant="destructive" className={cn(seniorMode && "min-h-12 text-lg")} onClick={confirmDelete} disabled={deletingSession}>
              {deletingSession ? "正在删除…" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingRole !== null}
        onOpenChange={(open) => {
          if (!open) setPendingRole(null);
        }}
      >
        <DialogContent showCloseButton={!seniorMode} className={cn("sm:max-w-md", seniorMode && "p-5")}>
          <DialogHeader>
            <DialogTitle className={cn(seniorMode && "text-2xl")}>切换到{pendingRole ? roleLabel(pendingRole) : ""}</DialogTitle>
            <DialogDescription className={cn(seniorMode && "text-lg leading-8")}>
              切换后会显示适合该身份的功能。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className={cn("mt-5", seniorMode && "flex-row justify-end gap-3 p-5")}>
            <Button variant="outline" className={cn(seniorMode && "min-h-12 text-lg")} onClick={() => setPendingRole(null)}>
              取消
            </Button>
            <Button className={cn(seniorMode && "min-h-12 text-lg")} onClick={confirmRoleChange}>
              确认切换
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AccountDialog
        open={accountDialogOpen}
        onOpenChange={setAccountDialogOpen}
        seniorMode={seniorMode}
        onAuthenticated={(identity) => {
          clearAllData();
          setAccount(identity);
          setRole(identity.role);
          toast.show(identity.role === "doctor" ? "已登录医生账户。临床权限仍需患者授权。" : "已登录患者账户");
        }}
      />
      <AccountDeactivationDialog
        open={accountDeactivationOpen}
        onOpenChange={setAccountDeactivationOpen}
        seniorMode={seniorMode}
        onDeactivated={() => {
          setAccount(null);
          window.location.assign("/");
          setCurrentSession(null);
          closeRightPanel();
          toast.show("账户已停用，请使用其他账户登录。");
          onNavigate?.();
        }}
      />
      {account?.account_role === "patient" && <PrescriptionReviewAccessDialog
        open={prescriptionReviewAccessOpen}
        onOpenChange={setPrescriptionReviewAccessOpen}
        seniorMode={seniorMode}
      />}
      {account?.account_role === "doctor" && <DoctorPrescriptionReviewDialog
        open={doctorPrescriptionReviewOpen}
        onOpenChange={setDoctorPrescriptionReviewOpen}
        seniorMode={seniorMode}
      />}
      {account?.account_role === "doctor" && <DoctorCgaWorkspaceDialog
        open={doctorCgaWorkspaceOpen}
        onOpenChange={setDoctorCgaWorkspaceOpen}
        seniorMode={seniorMode}
      />}
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
  onRename: () => void;
  onDelete: () => void;
  onTogglePin: () => void;
  seniorMode: boolean;
}) {
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
          "absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-full bg-primary transition-opacity duration-[var(--motion-popover)] ease-[var(--motion-ease-out)]",
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
        seniorMode && "grid w-full grid-cols-3 gap-1.5 opacity-100"
      )}>
        <button
          type="button"
          className={cn(
            "p-1.5 rounded-lg hover:bg-background text-muted-foreground hover:text-foreground transition-colors",
            seniorMode && "inline-flex min-h-12 min-w-0 flex-col justify-center gap-0.5 px-1 text-lg leading-tight whitespace-normal"
          )}
          onClick={(e) => {
            e.stopPropagation();
            onRename();
          }}
          aria-label="重命名"
        >
          <Pencil className="size-3.5" />
          {seniorMode && <span>重命名</span>}
        </button>
        <button
          type="button"
          className={cn(
            "p-1.5 rounded-lg hover:bg-background text-muted-foreground hover:text-foreground transition-colors",
            seniorMode && "inline-flex min-h-12 min-w-0 flex-col justify-center gap-0.5 px-1 text-lg leading-tight whitespace-normal"
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
            seniorMode && "inline-flex min-h-12 min-w-0 flex-col justify-center gap-0.5 px-1 text-lg leading-tight whitespace-normal"
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
