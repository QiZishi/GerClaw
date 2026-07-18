"use client";

import { useEffect, useState } from "react";
import { Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import { listAuthorizedPatients } from "@/services/gerclaw/consent";
import type { PatientGrantResource } from "@/services/gerclaw/consent";
import type { DoctorPatientAccess } from "@/services/gerclaw/schemas";

const scopeLabels: Record<PatientGrantResource, string> = {
  health_profile_read: "健康画像",
  cga_report_read: "CGA 报告",
  prescription_draft_review: "处方草案",
};

function formattedExpiry(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value));
}

export function DoctorPatientDirectoryDialog({
  open,
  onOpenChange,
  seniorMode,
  onSelectPatient,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
  onSelectPatient: (patientActorId: string, resourceScope: PatientGrantResource) => void;
}) {
  const [patients, setPatients] = useState<DoctorPatientAccess[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  useEffect(() => {
    if (!open) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setLoading(true);
      setError(null);
      try {
        const result = await listAuthorizedPatients();
        if (active) setPatients(result.items);
      } catch {
        if (active) {
          setPatients([]);
          setError("暂时无法读取患者列表。");
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [open]);

  async function copyPatientCode(patientActorId: string) {
    try {
      await navigator.clipboard.writeText(patientActorId);
      setCopiedId(patientActorId);
    } catch {
      setError("暂时无法复制患者代码。");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-3xl", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>患者列表</DialogTitle>
          <DialogDescription className={textClass}>仅显示当前授权给您的患者。</DialogDescription>
        </DialogHeader>
        {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
        {loading && <InlineLoadingState message="正在读取患者列表" className="min-h-24" />}
        {!loading && !error && (patients.length === 0 ? (
          <p className={cn("py-5 text-center text-muted-foreground", textClass)}>暂无已授权患者</p>
        ) : (
          <ul className="grid gap-3" aria-label="已授权患者">
            {patients.map((patient) => (
              <li key={patient.patient_actor_id} className="rounded-xl border p-3">
                <div className="flex items-center justify-between gap-2">
                  <code className={cn("min-w-0 truncate font-mono", seniorMode && "text-base")}>{patient.patient_actor_id}</code>
                  <Button type="button" size="sm" variant="ghost" className={cn("shrink-0", seniorMode && "min-h-12 text-base")} onClick={() => void copyPatientCode(patient.patient_actor_id)}>
                    <Copy className="size-4" />{copiedId === patient.patient_actor_id ? "已复制" : "复制代码"}
                  </Button>
                </div>
                <div className={cn("mt-2 flex flex-wrap gap-2", textClass)}>
                  {patient.grants.map((grant) => (
                    <span key={grant.resource_scope} className="rounded-full bg-muted px-2.5 py-1 text-muted-foreground">
                      {scopeLabels[grant.resource_scope]} · 至 {formattedExpiry(grant.expires_at)}
                    </span>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {patient.grants.map((grant) => (
                    <Button
                      key={grant.resource_scope}
                      type="button"
                      size="sm"
                      variant="outline"
                      className={cn(seniorMode && "min-h-12 text-base")}
                      onClick={() => onSelectPatient(patient.patient_actor_id, grant.resource_scope)}
                    >
                      {grant.resource_scope === "health_profile_read"
                        ? "查看画像"
                        : grant.resource_scope === "cga_report_read"
                          ? "查看 CGA"
                          : "复核草案"}
                    </Button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        ))}
      </DialogContent>
    </Dialog>
  );
}
