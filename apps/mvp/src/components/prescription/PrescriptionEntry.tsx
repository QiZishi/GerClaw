"use client";

import { useState } from "react";
import type { PatientSummary, PrescriptionReport as PrescriptionReportData, PrescriptionStage } from "@/types";
import { CollectionForm } from "./CollectionForm";
import { GeneratingOverlay } from "./GeneratingOverlay";
import { PrescriptionReport } from "./PrescriptionReport";

const emptyReport: PrescriptionReportData = {
  id: "",
  sessionId: "",
  createdAt: Date.now(),
  patient: {},
  diagnosis: {
    summary: "暂无诊断数据",
    problems: [],
    suspectedDiagnoses: [],
    riskFactors: [],
  },
  sections: [],
  citations: [],
  disclaimer: "内容由 AI 生成，仅供参考。身体不适请及时就医。",
};

interface PrescriptionEntryProps {
  /** 初始阶段，默认 done（直接显示报告） */
  initialStage?: PrescriptionStage;
  /** 初始患者信息（可选） */
  initialPatient?: PatientSummary;
}

/**
 * §6 五大处方 — 三入口状态分发器
 * 根据 PrescriptionStage 切换 CollectionForm / GeneratingOverlay / PrescriptionReport
 * 默认展示 done 阶段（mock 报告）
 */
export function PrescriptionEntry({
  initialStage = "done",
  initialPatient,
}: PrescriptionEntryProps) {
  const [stage, setStage] = useState<PrescriptionStage>(initialStage);
  const [, setPatient] = useState<PatientSummary | undefined>(initialPatient);

  if (stage === "collecting" || stage === "idle") {
    return (
      <CollectionForm
        onComplete={(data) => {
          setPatient(data);
          setStage("generating");
        }}
        onCancel={() => setStage("done")}
      />
    );
  }

  if (stage === "generating" || stage === "validating") {
    return (
      <GeneratingOverlay
        onDone={() => setStage("done")}
      />
    );
  }

  if (stage === "failed") {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
        <div className="text-sm text-destructive">生成失败，请稍后重试</div>
        <button
          type="button"
          onClick={() => setStage("collecting")}
          className="text-xs text-primary underline-offset-4 hover:underline"
        >
          重新填写信息
        </button>
      </div>
    );
  }

  // done / completing / 默认：展示报告
  return <PrescriptionReport report={emptyReport} />;
}
