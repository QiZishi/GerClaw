"use client";

import { useState } from "react";
import {
  BookOpen,
  ChevronRight,
  ClipboardList,
  HeartPulse,
  Pill,
  Salad,
  Sparkles,
  UserRound,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";
import { detectHighRiskSymptoms } from "@/lib/security";
import { cn } from "@/lib/utils";
import type {
  PatientSummary,
  PrescriptionReport as PrescriptionReportData,
  PrescriptionSection,
} from "@/types";
import { Disclaimer } from "./Disclaimer";
import { EmergencyAlert } from "./EmergencyAlert";
import { VoiceReadButton } from "./VoiceReadButton";

interface PrescriptionReportProps {
  report: PrescriptionReportData;
}

const SECTION_ICONS: Record<string, typeof Pill> = {
  drug: Pill,
  exercise: HeartPulse,
  nutrition: Salad,
  psychology: Sparkles,
  rehabilitation: ClipboardList,
  medication: Pill,
  smokingAlcohol: ClipboardList,
};

/**
 * §6 五大处方报告预览
 * 左侧目录导航（5 类处方 + 患者摘要 + 健康诊断）
 * 右侧 PrescriptionSection 渲染
 * 含 Disclaimer + EmergencyAlert + 导出 + 朗读
 */
export function PrescriptionReport({ report }: PrescriptionReportProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [activeKey, setActiveKey] = useState<string>("patient");

  // 高风险症状检测（基于患者主诉）
  const riskCheck = detectHighRiskSymptoms(
    `${report.patient.chiefComplaint ?? ""} ${report.diagnosis.summary}`
  );

  const navItems: { key: string; label: string; icon: typeof UserRound }[] = [
    { key: "patient", label: "患者摘要", icon: UserRound },
    { key: "diagnosis", label: "健康诊断", icon: BookOpen },
    ...report.sections.map((s) => ({
      key: s.type,
      label: s.title,
      icon: SECTION_ICONS[s.type],
    })),
  ];

  return (
    <div className="flex flex-col h-full">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium truncate">五大处方报告</span>
          <Badge variant="secondary" className="shrink-0">
            预览
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <VoiceReadButton text={report.diagnosis.summary} />
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* 左侧目录 */}
        <nav
          aria-label="处方目录"
          className={cn(
            "w-32 shrink-0 border-r border-border overflow-y-auto py-2",
            seniorMode && "w-36"
          )}
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activeKey === item.key;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setActiveKey(item.key)}
                className={cn(
                  "flex w-full items-center gap-1.5 px-2 py-2 text-left text-sm transition-colors",
                  seniorMode && "text-base py-2.5",
                  active
                    ? "bg-primary/10 text-primary font-medium"
                    : "hover:bg-muted text-muted-foreground"
                )}
                aria-current={active ? "true" : undefined}
              >
                <Icon className="size-3.5 shrink-0" />
                <span className="truncate">{item.label}</span>
                {active && <ChevronRight className="size-3 ml-auto shrink-0" />}
              </button>
            );
          })}
        </nav>

        {/* 右侧内容 */}
        <ScrollArea className="flex-1 min-w-0">
          <div className="p-3 space-y-3">
            {activeKey === "patient" && (
              <PatientSummaryView patient={report.patient} />
            )}
            {activeKey === "diagnosis" && (
              <DiagnosisView report={report} hasHighRisk={riskCheck.hasHighRisk} />
            )}
            {report.sections.map(
              (s) =>
                activeKey === s.type && (
                  <SectionView key={s.type} section={s} />
                )
            )}

            {/* 始终展示免责声明 */}
            <Disclaimer className="mt-4" />
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

/** 患者摘要视图 */
function PatientSummaryView({ patient }: { patient: PatientSummary }) {
  const asString = (v: string | string[] | undefined): string | undefined =>
    Array.isArray(v) ? v.join("、") : v;

  const fields: { label: string; value?: string }[] = [
    {
      label: "基本信息",
      value: `${patient.gender === "female" ? "女" : "男"}，${patient.age ?? "?"} 岁`,
    },
    { label: "主诉", value: patient.chiefComplaint },
    {
      label: "病史",
      value: asString(patient.history),
    },
    {
      label: "当前用药",
      value: asString(patient.currentMedications)?.replace(/、/g, "；"),
    },
    { label: "过敏史", value: asString(patient.allergies) ?? "无" },
  ];

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold flex items-center gap-1.5">
        <UserRound className="size-4" />
        患者摘要
      </h3>
      <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-1.5">
        {fields.map((f) => (
          <div key={f.label} className="text-xs">
            <span className="text-muted-foreground mr-2">{f.label}：</span>
            <span>{f.value || "—"}</span>
          </div>
        ))}
        {patient.vitals && (
          <Separator className="my-2" />
        )}
        {patient.vitals && (
          <div className="flex flex-wrap gap-2">
            {Object.entries(patient.vitals).map(([k, v]) => (
              <Badge key={k} variant="outline" className="text-xs">
                {k}: {String(v)}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** 健康诊断视图 */
function DiagnosisView({
  report,
  hasHighRisk,
}: {
  report: PrescriptionReportData;
  hasHighRisk: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold flex items-center gap-1.5 mb-2">
          <BookOpen className="size-4" />
          健康诊断（疑似）
        </h3>
        <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2">
          <p className="text-xs leading-relaxed">{report.diagnosis.summary}</p>
          <Separator />
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">
              主要问题
            </div>
            <ul className="text-xs space-y-1 list-disc pl-4">
              {report.diagnosis.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
          <Separator />
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">
              疑似诊断
            </div>
            <div className="flex flex-wrap gap-1">
              {report.diagnosis.suspectedDiagnoses.map((d) => (
                <Badge key={d} variant="secondary" className="text-xs">
                  {d}
                </Badge>
              ))}
            </div>
          </div>
          <Separator />
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">
              风险因素
            </div>
            <div className="flex flex-wrap gap-1">
              {report.diagnosis.riskFactors.map((r) => (
                <Badge key={r} variant="outline" className="text-xs">
                  {r}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </div>

      {hasHighRisk && <EmergencyAlert />}

      <p className="text-[10px] text-muted-foreground">
        注：所有诊断均为&ldquo;疑似&rdquo;，禁止作为确定性诊断依据。请就医明确诊断。
      </p>
    </div>
  );
}

/** 单类处方可视化 */
function SectionView({ section }: { section: PrescriptionSection }) {
  const Icon = SECTION_ICONS[section.type];
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold flex items-center gap-1.5">
        <Icon className="size-4" />
        {section.title}
      </h3>
      <p className="text-xs text-muted-foreground leading-relaxed">
        {section.summary}
      </p>
      <div className="space-y-2">
        {section.items.map((item) => (
          <div
            key={item.name}
            className="rounded-lg border border-border bg-card p-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{item.name}</span>
            </div>
            <div className="text-xs text-muted-foreground mt-1 leading-relaxed">
              {item.detail}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[11px]">
              {item.dosage && (
                <span>
                  <span className="text-muted-foreground">剂量：</span>
                  {item.dosage}
                </span>
              )}
              {item.frequency && (
                <span>
                  <span className="text-muted-foreground">频次：</span>
                  {item.frequency}
                </span>
              )}
              {item.duration && (
                <span>
                  <span className="text-muted-foreground">疗程：</span>
                  {item.duration}
                </span>
              )}
            </div>
            {item.precautions && (
              <div className="mt-2 text-[11px]">
                <span className="text-muted-foreground">注意事项：</span>
                <span className="text-amber-700 dark:text-amber-300">
                  {Array.isArray(item.precautions) ? item.precautions.join("；") : item.precautions}
                </span>
              </div>
            )}
            {item.evidence && item.evidence.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {item.evidence.map((ev) => (
                  <Badge
                    key={ev.title}
                    variant="outline"
                    className="text-[10px] gap-0.5"
                  >
                    <BookOpen className="size-2.5" />
                    {ev.title}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {section.evidence && section.evidence.length > 0 && (
        <div className="text-[10px] text-muted-foreground pt-1">
          循证来源：{section.evidence.map((e) => e.title).join("；")}
        </div>
      )}
    </div>
  );
}
