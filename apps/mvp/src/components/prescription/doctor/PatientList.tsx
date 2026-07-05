"use client";

import { useMemo, useState } from "react";
import {
  CalendarClock,
  ChevronRight,
  Search,
  UserRound,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAppStore } from "@/stores/appStore";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface Patient {
  id: string;
  name: string;
  age: number;
  gender: "男" | "女";
  chiefComplaint: string;
  conditions: string[];
  currentMedications: string[];
  recentCgaScore?: number;
  status: "待评估" | "评估中" | "已完成";
  lastVisit: string;
}

const STATUS_VARIANT: Record<
  Patient["status"],
  "default" | "secondary" | "outline"
> = {
  待评估: "secondary",
  评估中: "default",
  已完成: "outline",
};

const EMPTY_PATIENTS: Patient[] = [];

interface PatientListProps {
  className?: string;
  onSelectPatient?: (patient: Patient) => void;
  selectedPatientId?: string | null;
}

export function PatientList({
  className,
  onSelectPatient,
  selectedPatientId,
}: PatientListProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return EMPTY_PATIENTS;
    return EMPTY_PATIENTS.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.chiefComplaint.toLowerCase().includes(q) ||
        p.conditions.some((c) => c.toLowerCase().includes(q))
    );
  }, [query]);

  return (
    <div className={cn("flex flex-col h-full", className)}>
      <header className="px-4 py-3 border-b border-border">
        <div className="flex items-center justify-between mb-2">
          <h2
            className={cn(
              "font-semibold flex items-center gap-2",
              seniorMode ? "text-lg" : "text-base"
            )}
          >
            <UserRound className="size-4" />
            患者列表
          </h2>
          <Badge variant="secondary">{EMPTY_PATIENTS.length} 位患者</Badge>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="搜索姓名/主诉/诊断"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 pl-7"
            aria-label="搜索患者"
          />
        </div>
      </header>

      <ScrollArea className="flex-1 min-h-0">
        <ul className="p-2 space-y-1.5">
          {filtered.length === 0 && (
            <li className="text-center text-xs text-muted-foreground py-8">
              暂无患者数据
            </li>
          )}
          {filtered.map((p) => (
            <PatientListItem
              key={p.id}
              patient={p}
              active={selectedPatientId === p.id}
              seniorMode={seniorMode}
              onSelect={() => onSelectPatient?.(p)}
            />
          ))}
        </ul>
      </ScrollArea>
    </div>
  );
}

interface PatientListItemProps {
  patient: Patient;
  active: boolean;
  seniorMode: boolean;
  onSelect: () => void;
}

function PatientListItem({
  patient,
  active,
  seniorMode,
  onSelect,
}: PatientListItemProps) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "w-full text-left rounded-lg border px-3 py-2.5 transition-colors",
          active
            ? "border-primary bg-primary/5"
            : "border-border bg-card hover:bg-muted/50",
          seniorMode && "py-3"
        )}
        aria-pressed={active}
      >
        <div className="flex items-start gap-2">
          <div
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
              active
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground"
            )}
          >
            {patient.name.slice(0, 1)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={cn(
                  "font-medium",
                  seniorMode ? "text-base" : "text-sm"
                )}
              >
                {patient.name}
              </span>
              <span className="text-xs text-muted-foreground">
                {patient.gender} · {patient.age} 岁
              </span>
              <Badge
                variant={STATUS_VARIANT[patient.status]}
                className="text-[10px] py-0"
              >
                {patient.status}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
              {patient.chiefComplaint}
            </p>
            <div className="flex items-center gap-1 flex-wrap mt-1.5">
              {patient.conditions.slice(0, 3).map((c) => (
                <span
                  key={c}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                >
                  {c}
                </span>
              ))}
            </div>
            <div className="flex items-center gap-3 mt-1.5 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <CalendarClock className="size-3" />
                {formatDate(new Date(patient.lastVisit).getTime())}
              </span>
              {patient.recentCgaScore !== undefined && (
                <span>CGA: {patient.recentCgaScore}</span>
              )}
              <span>{patient.currentMedications.length} 种用药</span>
            </div>
          </div>
          <ChevronRight className="size-4 text-muted-foreground shrink-0 mt-1" />
        </div>
      </button>
    </li>
  );
}
