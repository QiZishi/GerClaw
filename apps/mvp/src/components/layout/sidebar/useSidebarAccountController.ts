"use client";

import { useEffect, useState } from "react";

import type { SidebarAccountMenuActions } from "@/components/layout/sidebar/SidebarAccountMenu";
import { toast } from "@/components/ui/toast";
import {
  exitGuestSession,
  getAccountIdentity,
  logoutAccount,
  switchAdministratorView,
  type AccountIdentity,
} from "@/services/account";
import type { PatientGrantResource } from "@/services/gerclaw/consent";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";

interface SidebarAccountControllerOptions {
  mounted: boolean;
  onNavigate?: () => void;
  openHistory: () => void;
  setSeniorMode: (enabled: boolean) => void;
  toggleTheme: () => void;
}

export function useSidebarAccountController({
  mounted,
  onNavigate,
  openHistory,
  setSeniorMode,
  toggleTheme,
}: SidebarAccountControllerOptions) {
  const setCurrentSession = useAppStore((state) => state.setCurrentSession);
  const setRole = useAppStore((state) => state.setRole);
  const setGuestMode = useAppStore((state) => state.setGuestMode);
  const setRightPanel = useAppStore((state) => state.setRightPanel);
  const closeRightPanel = useAppStore((state) => state.closeRightPanel);
  const clearAllData = useChatStore((state) => state.clearAllData);
  const [account, setAccount] = useState<AccountIdentity | null>(null);
  const [accountDialogOpen, setAccountDialogOpen] = useState(false);
  const [accountDeactivationOpen, setAccountDeactivationOpen] = useState(false);
  const [prescriptionReviewAccessOpen, setPrescriptionReviewAccessOpen] =
    useState(false);
  const [doctorPrescriptionReviewOpen, setDoctorPrescriptionReviewOpen] =
    useState(false);
  const [doctorMedicationReviewOpen, setDoctorMedicationReviewOpen] =
    useState(false);
  const [doctorRiskAlertOpen, setDoctorRiskAlertOpen] = useState(false);
  const [doctorCgaWorkspaceOpen, setDoctorCgaWorkspaceOpen] = useState(false);
  const [doctorChronicCareOpen, setDoctorChronicCareOpen] = useState(false);
  const [doctorHealthProfileOpen, setDoctorHealthProfileOpen] = useState(false);
  const [doctorPatientDirectoryOpen, setDoctorPatientDirectoryOpen] =
    useState(false);
  const [runtimeApprovalReviewOpen, setRuntimeApprovalReviewOpen] =
    useState(false);
  const [selectedPatientActorId, setSelectedPatientActorId] = useState<
    string | null
  >(null);

  useEffect(() => {
    if (!mounted) return;
    void getAccountIdentity().then((identity) => {
      if (!identity) return;
      setAccount(identity);
      if (useAppStore.getState().role !== identity.role) {
        setRole(identity.role);
      }
    });
  }, [mounted, setRole]);

  const openSettings = () => {
    setRightPanel("settings");
    onNavigate?.();
  };

  const openHelp = () => {
    setRightPanel("help");
    onNavigate?.();
  };

  const exit = async () => {
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

  const switchWorkspace = async (targetRole: "patient" | "doctor") => {
    if (useAppStore.getState().isGuest) {
      const changed = setRole(targetRole);
      if (!changed) return;
      setGuestMode(true);
      clearAllData();
      setCurrentSession(null);
      closeRightPanel();
      toast.show(targetRole === "doctor" ? "已切换到医生端" : "已切换到患者端");
      onNavigate?.();
      return;
    }
    try {
      await switchAdministratorView(targetRole);
      clearAllData();
      window.location.assign("/");
    } catch {
      toast.show("工作区切换未完成，请稍后重试。");
    }
  };

  const copyReviewCode = async (kind: "医生" | "患者") => {
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
  };

  const closeSelectedPatientWorkspace = (
    setOpen: (open: boolean) => void,
    open: boolean,
  ) => {
    setOpen(open);
    if (!open) setSelectedPatientActorId(null);
  };

  const openAuthorizedPatientWorkspace = (
    patientActorId: string,
    resourceScope: PatientGrantResource,
  ) => {
    setSelectedPatientActorId(patientActorId);
    setDoctorPatientDirectoryOpen(false);
    const setters: Record<
      PatientGrantResource,
      (open: boolean) => void
    > = {
      health_profile_read: setDoctorHealthProfileOpen,
      cga_report_read: setDoctorCgaWorkspaceOpen,
      prescription_draft_review: setDoctorPrescriptionReviewOpen,
      risk_alert_read: setDoctorRiskAlertOpen,
      chronic_care_read: setDoctorChronicCareOpen,
      medication_review_read: setDoctorMedicationReviewOpen,
    };
    setters[resourceScope](true);
  };

  const menuActions: SidebarAccountMenuActions = {
    openAccount: () => setAccountDialogOpen(true),
    setSeniorMode,
    toggleTheme,
    openHistory,
    openSettings,
    openHelp,
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
    openAdminConsole: () => window.location.assign("/?workspace=admin"),
    openPatientWorkspace: () => void switchWorkspace("patient"),
    openDoctorWorkspace: () => void switchWorkspace("doctor"),
    deactivateAccount: () => setAccountDeactivationOpen(true),
    exit: () => void exit(),
  };

  return {
    account,
    menuActions,
    dialogs: {
      selectedPatientActorId,
      accountDialogOpen,
      accountDeactivationOpen,
      prescriptionReviewAccessOpen,
      doctorPrescriptionReviewOpen,
      doctorMedicationReviewOpen,
      doctorRiskAlertOpen,
      doctorCgaWorkspaceOpen,
      doctorChronicCareOpen,
      doctorHealthProfileOpen,
      doctorPatientDirectoryOpen,
      runtimeApprovalReviewOpen,
      onAccountDialogOpenChange: setAccountDialogOpen,
      onAccountDeactivationOpenChange: setAccountDeactivationOpen,
      onPrescriptionReviewAccessOpenChange: setPrescriptionReviewAccessOpen,
      onDoctorPrescriptionReviewOpenChange: (open: boolean) =>
        closeSelectedPatientWorkspace(setDoctorPrescriptionReviewOpen, open),
      onDoctorMedicationReviewOpenChange: (open: boolean) =>
        closeSelectedPatientWorkspace(setDoctorMedicationReviewOpen, open),
      onDoctorRiskAlertOpenChange: (open: boolean) =>
        closeSelectedPatientWorkspace(setDoctorRiskAlertOpen, open),
      onDoctorCgaWorkspaceOpenChange: (open: boolean) =>
        closeSelectedPatientWorkspace(setDoctorCgaWorkspaceOpen, open),
      onDoctorChronicCareOpenChange: (open: boolean) =>
        closeSelectedPatientWorkspace(setDoctorChronicCareOpen, open),
      onDoctorHealthProfileOpenChange: (open: boolean) =>
        closeSelectedPatientWorkspace(setDoctorHealthProfileOpen, open),
      onDoctorPatientDirectoryOpenChange: setDoctorPatientDirectoryOpen,
      onRuntimeApprovalReviewOpenChange: setRuntimeApprovalReviewOpen,
      onAuthenticated: (identity: AccountIdentity) => {
        clearAllData();
        setAccount(identity);
        setGuestMode(false);
        setRole(identity.role);
        toast.show(
          identity.role === "doctor"
            ? "已登录医生账户。临床权限仍需患者授权。"
            : "已登录患者账户",
        );
      },
      onDeactivated: () => {
        setAccount(null);
        window.location.assign("/");
        setCurrentSession(null);
        closeRightPanel();
        toast.show("账户已停用，请使用其他账户登录。");
        onNavigate?.();
      },
      onSelectPatient: openAuthorizedPatientWorkspace,
    },
  };
}
