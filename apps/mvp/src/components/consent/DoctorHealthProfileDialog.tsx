"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { readAuthorizedHealthProfile } from "@/services/gerclaw/doctor-health-profile";
import type { HealthProfile, MemoryFact } from "@/services/gerclaw/schemas";

const accountIdPattern = /^usr_account_[a-f0-9]{32}$/;
const categoryNames: Record<MemoryFact["category"], string> = {
  basic_info: "基本资料",
  allergy: "过敏史",
  condition: "病史与慢病",
  medication: "用药情况",
  vital_sign: "生命体征",
  assessment: "评估记录",
  event: "重要健康事件",
  social: "照护与社会支持",
  preference: "照护偏好",
  goal: "健康目标",
};

export function DoctorHealthProfileDialog({
  open,
  onOpenChange,
  seniorMode,
  initialPatientActorId = null,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
  initialPatientActorId?: string | null;
}) {
  const [patientActorId, setPatientActorId] = useState("");
  const [profile, setProfile] = useState<HealthProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";
  const sections = useMemo(() => {
    const grouped = new Map<MemoryFact["category"], MemoryFact[]>();
    for (const fact of profile?.facts ?? []) {
      if (fact.status !== "confirmed") continue;
      grouped.set(fact.category, [...(grouped.get(fact.category) ?? []), fact]);
    }
    return [...grouped.entries()];
  }, [profile]);

  function close(nextOpen: boolean) {
    if (!nextOpen) {
      setPatientActorId("");
      setProfile(null);
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function load() {
    if (loading || !accountIdPattern.test(patientActorId.trim())) return;
    setLoading(true);
    setError(null);
    try {
      setProfile(await readAuthorizedHealthProfile(patientActorId));
    } catch {
      setProfile(null);
      setError("未找到可查看的健康画像，或患者尚未授权。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open || !initialPatientActorId || !accountIdPattern.test(initialPatientActorId)) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setPatientActorId(initialPatientActorId);
      setLoading(true);
      setError(null);
      try {
        const nextProfile = await readAuthorizedHealthProfile(initialPatientActorId);
        if (active) setProfile(nextProfile);
      } catch {
        if (active) {
          setProfile(null);
          setError("未找到可查看的健康画像，或患者尚未授权。");
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [initialPatientActorId, open]);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-3xl", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>患者健康画像</DialogTitle>
          <DialogDescription className={textClass}>输入患者代码后查看已授权、已确认的健康信息。</DialogDescription>
        </DialogHeader>
        <div className="mt-3 flex gap-2">
          <div className="min-w-0 flex-1">
            <Label htmlFor="profile-patient-code" className="sr-only">患者代码</Label>
            <Input
              id="profile-patient-code"
              value={patientActorId}
              onChange={(event) => setPatientActorId(event.target.value.trim())}
              placeholder="患者代码"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              maxLength={44}
              className={cn("font-mono", seniorMode && "h-12 text-base")}
            />
          </div>
          <Button type="button" disabled={loading || !accountIdPattern.test(patientActorId)} onClick={() => void load()} className={cn(seniorMode && "min-h-12 text-lg")}>
            查看画像
          </Button>
        </div>
        {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
        {loading && <InlineLoadingState message="正在读取健康画像" className="min-h-24" />}
        {profile && !loading && (sections.length === 0 ? (
          <p className={cn("py-5 text-center text-muted-foreground", textClass)}>暂无已确认的健康信息</p>
        ) : (
          <div className="grid gap-4">
            {sections.map(([category, facts]) => (
              <section key={category} aria-labelledby={`doctor-profile-${category}`}>
                <h3 id={`doctor-profile-${category}`} className={cn("font-semibold", seniorMode && "text-xl")}>{categoryNames[category]}</h3>
                <ul className="mt-2 grid gap-2">
                  {facts.map((fact) => <li key={fact.id} className={cn("rounded-xl border p-3", textClass)}>{fact.statement}</li>)}
                </ul>
              </section>
            ))}
          </div>
        ))}
      </DialogContent>
    </Dialog>
  );
}
