"use client";

import { AccountDeactivationDialog } from "@/components/account/AccountDeactivationDialog";
import { AccountDialog } from "@/components/account/AccountDialog";
import { DoctorCgaWorkspaceDialog } from "@/components/consent/DoctorCgaWorkspaceDialog";
import { DoctorChronicCareDialog } from "@/components/consent/DoctorChronicCareDialog";
import { DoctorHealthProfileDialog } from "@/components/consent/DoctorHealthProfileDialog";
import { DoctorMedicationReviewDialog } from "@/components/consent/DoctorMedicationReviewDialog";
import { DoctorPatientDirectoryDialog } from "@/components/consent/DoctorPatientDirectoryDialog";
import { DoctorPrescriptionReviewDialog } from "@/components/consent/DoctorPrescriptionReviewDialog";
import { DoctorRiskAlertDialog } from "@/components/consent/DoctorRiskAlertDialog";
import { PrescriptionReviewAccessDialog } from "@/components/consent/PrescriptionReviewAccessDialog";
import { RuntimeApprovalReviewDialog } from "@/components/runtime/RuntimeApprovalReviewDialog";
import type { AccountIdentity } from "@/services/account";
import type { PatientGrantResource } from "@/services/gerclaw/consent";

interface SidebarAccountDialogsProps {
  account: AccountIdentity | null;
  seniorMode: boolean;
  selectedPatientActorId: string | null;
  accountDialogOpen: boolean;
  accountDeactivationOpen: boolean;
  prescriptionReviewAccessOpen: boolean;
  doctorPrescriptionReviewOpen: boolean;
  doctorMedicationReviewOpen: boolean;
  doctorRiskAlertOpen: boolean;
  doctorCgaWorkspaceOpen: boolean;
  doctorChronicCareOpen: boolean;
  doctorHealthProfileOpen: boolean;
  doctorPatientDirectoryOpen: boolean;
  runtimeApprovalReviewOpen: boolean;
  onAccountDialogOpenChange: (open: boolean) => void;
  onAccountDeactivationOpenChange: (open: boolean) => void;
  onPrescriptionReviewAccessOpenChange: (open: boolean) => void;
  onDoctorPrescriptionReviewOpenChange: (open: boolean) => void;
  onDoctorMedicationReviewOpenChange: (open: boolean) => void;
  onDoctorRiskAlertOpenChange: (open: boolean) => void;
  onDoctorCgaWorkspaceOpenChange: (open: boolean) => void;
  onDoctorChronicCareOpenChange: (open: boolean) => void;
  onDoctorHealthProfileOpenChange: (open: boolean) => void;
  onDoctorPatientDirectoryOpenChange: (open: boolean) => void;
  onRuntimeApprovalReviewOpenChange: (open: boolean) => void;
  onAuthenticated: (identity: AccountIdentity) => void;
  onDeactivated: () => void;
  onSelectPatient: (
    patientActorId: string,
    resourceScope: PatientGrantResource,
  ) => void;
}

export function SidebarAccountDialogs(props: SidebarAccountDialogsProps) {
  const isPatientAccount = props.account?.account_role === "patient";
  const isDoctorAccount = props.account?.account_role === "doctor";
  return (
    <>
      <AccountDialog
        open={props.accountDialogOpen}
        onOpenChange={props.onAccountDialogOpenChange}
        seniorMode={props.seniorMode}
        onAuthenticated={props.onAuthenticated}
      />
      <AccountDeactivationDialog
        open={props.accountDeactivationOpen}
        onOpenChange={props.onAccountDeactivationOpenChange}
        seniorMode={props.seniorMode}
        onDeactivated={props.onDeactivated}
      />
      {isPatientAccount && (
        <PrescriptionReviewAccessDialog
          open={props.prescriptionReviewAccessOpen}
          onOpenChange={props.onPrescriptionReviewAccessOpenChange}
          seniorMode={props.seniorMode}
        />
      )}
      {isDoctorAccount && (
        <>
          <DoctorPrescriptionReviewDialog
            open={props.doctorPrescriptionReviewOpen}
            onOpenChange={props.onDoctorPrescriptionReviewOpenChange}
            seniorMode={props.seniorMode}
            initialPatientActorId={props.selectedPatientActorId}
          />
          <DoctorMedicationReviewDialog
            open={props.doctorMedicationReviewOpen}
            onOpenChange={props.onDoctorMedicationReviewOpenChange}
            seniorMode={props.seniorMode}
            initialPatientActorId={props.selectedPatientActorId}
          />
          <DoctorRiskAlertDialog
            open={props.doctorRiskAlertOpen}
            onOpenChange={props.onDoctorRiskAlertOpenChange}
            seniorMode={props.seniorMode}
            initialPatientActorId={props.selectedPatientActorId}
          />
          <DoctorChronicCareDialog
            open={props.doctorChronicCareOpen}
            onOpenChange={props.onDoctorChronicCareOpenChange}
            seniorMode={props.seniorMode}
            initialPatientActorId={props.selectedPatientActorId}
          />
          <RuntimeApprovalReviewDialog
            open={props.runtimeApprovalReviewOpen}
            onOpenChange={props.onRuntimeApprovalReviewOpenChange}
            seniorMode={props.seniorMode}
          />
          <DoctorCgaWorkspaceDialog
            open={props.doctorCgaWorkspaceOpen}
            onOpenChange={props.onDoctorCgaWorkspaceOpenChange}
            seniorMode={props.seniorMode}
            initialPatientActorId={props.selectedPatientActorId}
          />
          <DoctorHealthProfileDialog
            open={props.doctorHealthProfileOpen}
            onOpenChange={props.onDoctorHealthProfileOpenChange}
            seniorMode={props.seniorMode}
            initialPatientActorId={props.selectedPatientActorId}
          />
          <DoctorPatientDirectoryDialog
            open={props.doctorPatientDirectoryOpen}
            onOpenChange={props.onDoctorPatientDirectoryOpenChange}
            seniorMode={props.seniorMode}
            onSelectPatient={props.onSelectPatient}
          />
        </>
      )}
    </>
  );
}
