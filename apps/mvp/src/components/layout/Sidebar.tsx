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
import { useChatStore } from "@/stores/chatStore";
import { useTheme } from "@/context/ThemeProvider";
import { cn } from "@/lib/utils";
import { SidebarSessionHistory } from "@/components/layout/sidebar/SidebarSessionHistory";
import { SidebarSessionDialogs } from "@/components/layout/sidebar/SidebarSessionDialogs";
import { SidebarAccountMenu } from "@/components/layout/sidebar/SidebarAccountMenu";
import { SidebarAccountDialogs } from "@/components/layout/sidebar/SidebarAccountDialogs";
import { useSidebarSessionController } from "@/components/layout/sidebar/useSidebarSessionController";
import { toast } from "@/components/ui/toast";
import type { PatientGrantResource } from "@/services/gerclaw/consent";
import {
  getAccountIdentity,
  exitGuestSession,
  logoutAccount,
  switchAdministratorView,
  type AccountIdentity,
} from "@/services/account";

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
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const setRole = useAppStore((s) => s.setRole);
  const setSeniorMode = useAppStore((s) => s.setSeniorMode);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const closeRightPanel = useAppStore((s) => s.closeRightPanel);
  const mainView = useAppStore((s) => s.mainView);
  const setMainView = useAppStore((s) => s.setMainView);
  const { resolvedTheme, toggleTheme } = useTheme();

  const clearAllData = useChatStore((s) => s.clearAllData);

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
  const [account, setAccount] = useState<AccountIdentity | null>(null);
  const [accountDialogOpen, setAccountDialogOpen] = useState(false);
  const [accountDeactivationOpen, setAccountDeactivationOpen] = useState(false);
  const [prescriptionReviewAccessOpen, setPrescriptionReviewAccessOpen] = useState(false);
  const [doctorPrescriptionReviewOpen, setDoctorPrescriptionReviewOpen] = useState(false);
  const [doctorMedicationReviewOpen, setDoctorMedicationReviewOpen] = useState(false);
  const [doctorRiskAlertOpen, setDoctorRiskAlertOpen] = useState(false);
  const [doctorCgaWorkspaceOpen, setDoctorCgaWorkspaceOpen] = useState(false);
  const [doctorChronicCareOpen, setDoctorChronicCareOpen] = useState(false);
  const [doctorHealthProfileOpen, setDoctorHealthProfileOpen] = useState(false);
  const [doctorPatientDirectoryOpen, setDoctorPatientDirectoryOpen] = useState(false);
  const [runtimeApprovalReviewOpen, setRuntimeApprovalReviewOpen] = useState(false);
  const [selectedPatientActorId, setSelectedPatientActorId] = useState<string | null>(null);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    void getAccountIdentity().then((identity) => {
      if (!identity) return;
      setAccount(identity);
      // Home already owns account-to-workspace hydration. A slower duplicate
      // identity response must not clear the conversation selected by Home.
      if (useAppStore.getState().role !== identity.role) {
        setRole(identity.role);
      }
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

  const handleOpenSettings = () => {
    setRightPanel("settings");
    onNavigate?.();
  };

  const handleShowHelp = () => {
    setRightPanel("help");
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

  function openAuthorizedPatientWorkspace(
    patientActorId: string,
    resourceScope: PatientGrantResource,
  ) {
    setSelectedPatientActorId(patientActorId);
    setDoctorPatientDirectoryOpen(false);
    if (resourceScope === "health_profile_read") {
      setDoctorHealthProfileOpen(true);
    } else if (resourceScope === "cga_report_read") {
      setDoctorCgaWorkspaceOpen(true);
    } else if (resourceScope === "prescription_draft_review") {
      setDoctorPrescriptionReviewOpen(true);
    } else if (resourceScope === "risk_alert_read") {
      setDoctorRiskAlertOpen(true);
    } else if (resourceScope === "chronic_care_read") {
      setDoctorChronicCareOpen(true);
    } else {
      setDoctorMedicationReviewOpen(true);
    }
  }

  function closeSelectedPatientWorkspace(
    setOpen: (open: boolean) => void,
    nextOpen: boolean,
  ) {
    setOpen(nextOpen);
    if (!nextOpen) setSelectedPatientActorId(null);
  }

  return (
    <aside
      className="flex h-full flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border"
      style={{ width: "100%" }}
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
        actions={{
          openAccount: () => setAccountDialogOpen(true),
          setSeniorMode,
          toggleTheme,
          openHistory: () => setPatientHistoryOpen(true),
          openSettings: handleOpenSettings,
          openHelp: handleShowHelp,
          openPrescriptionAccess: () => setPrescriptionReviewAccessOpen(true),
          copyPatientCode: () => void copyReviewCode("患者"),
          openPatientDirectory: () => setDoctorPatientDirectoryOpen(true),
          openHealthProfile: () => setDoctorHealthProfileOpen(true),
          openRuntimeApproval: () => setRuntimeApprovalReviewOpen(true),
          openPrescriptionReview: () => setDoctorPrescriptionReviewOpen(true),
          openMedicationReview: () => setDoctorMedicationReviewOpen(true),
          openRiskAlerts: () => setDoctorRiskAlertOpen(true),
          openChronicCare: () => setDoctorChronicCareOpen(true),
          openCgaWorkspace: () => setDoctorCgaWorkspaceOpen(true),
          copyDoctorCode: () => void copyReviewCode("医生"),
          openAdminConsole,
          openPatientWorkspace: () => void handleAdminWorkspace("patient"),
          openDoctorWorkspace: () => void handleAdminWorkspace("doctor"),
          deactivateAccount: () => setAccountDeactivationOpen(true),
          exit: () => void handleExit(),
        }}
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
        selectedPatientActorId={selectedPatientActorId}
        accountDialogOpen={accountDialogOpen}
        accountDeactivationOpen={accountDeactivationOpen}
        prescriptionReviewAccessOpen={prescriptionReviewAccessOpen}
        doctorPrescriptionReviewOpen={doctorPrescriptionReviewOpen}
        doctorMedicationReviewOpen={doctorMedicationReviewOpen}
        doctorRiskAlertOpen={doctorRiskAlertOpen}
        doctorCgaWorkspaceOpen={doctorCgaWorkspaceOpen}
        doctorChronicCareOpen={doctorChronicCareOpen}
        doctorHealthProfileOpen={doctorHealthProfileOpen}
        doctorPatientDirectoryOpen={doctorPatientDirectoryOpen}
        runtimeApprovalReviewOpen={runtimeApprovalReviewOpen}
        onAccountDialogOpenChange={setAccountDialogOpen}
        onAccountDeactivationOpenChange={setAccountDeactivationOpen}
        onPrescriptionReviewAccessOpenChange={setPrescriptionReviewAccessOpen}
        onDoctorPrescriptionReviewOpenChange={(open) =>
          closeSelectedPatientWorkspace(setDoctorPrescriptionReviewOpen, open)
        }
        onDoctorMedicationReviewOpenChange={(open) =>
          closeSelectedPatientWorkspace(setDoctorMedicationReviewOpen, open)
        }
        onDoctorRiskAlertOpenChange={(open) =>
          closeSelectedPatientWorkspace(setDoctorRiskAlertOpen, open)
        }
        onDoctorCgaWorkspaceOpenChange={(open) =>
          closeSelectedPatientWorkspace(setDoctorCgaWorkspaceOpen, open)
        }
        onDoctorChronicCareOpenChange={(open) =>
          closeSelectedPatientWorkspace(setDoctorChronicCareOpen, open)
        }
        onDoctorHealthProfileOpenChange={(open) =>
          closeSelectedPatientWorkspace(setDoctorHealthProfileOpen, open)
        }
        onDoctorPatientDirectoryOpenChange={setDoctorPatientDirectoryOpen}
        onRuntimeApprovalReviewOpenChange={setRuntimeApprovalReviewOpen}
        onAuthenticated={(identity) => {
          clearAllData();
          setAccount(identity);
          setRole(identity.role);
          toast.show(
            identity.role === "doctor"
              ? "已登录医生账户。临床权限仍需患者授权。"
              : "已登录患者账户",
          );
        }}
        onDeactivated={() => {
          setAccount(null);
          window.location.assign("/");
          setCurrentSession(null);
          closeRightPanel();
          toast.show("账户已停用，请使用其他账户登录。");
          onNavigate?.();
        }}
        onSelectPatient={openAuthorizedPatientWorkspace}
      />
    </aside>
  );
}
