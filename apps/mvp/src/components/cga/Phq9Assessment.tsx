"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import {
  completeCgaAssessment,
  getCgaAssessment,
  getCgaReport,
  startPhq9Assessment,
  submitCgaAnswer,
} from "@/services/gerclaw/cga";
import type { CgaAssessment, CgaReport } from "@/services/gerclaw/schemas";

const ACTIVE_ASSESSMENT_KEY = "gerclaw:cga:phq9:assessment";

interface Phq9AssessmentProps {
  onExit: () => void;
}

export function Phq9Assessment({ onExit }: Phq9AssessmentProps) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const [assessment, setAssessment] = useState<CgaAssessment | null>(null);
  const [report, setReport] = useState<CgaReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (newAssessment = false) => {
    setError(null);
    setSaving(true);
    try {
      const storedId = !newAssessment ? localStorage.getItem(ACTIVE_ASSESSMENT_KEY) : null;
      const next = storedId ? await getCgaAssessment(storedId) : await startPhq9Assessment();
      localStorage.setItem(ACTIVE_ASSESSMENT_KEY, next.assessment_id);
      setAssessment(next);
      setReport(next.status === "completed" ? await getCgaReport(next.assessment_id) : null);
    } catch {
      setError("评估服务暂时不可用。请检查网络后重试，已有进度不会被清除。");
    } finally {
      setSaving(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const choose = async (score: number) => {
    if (!assessment?.next_question || saving) return;
    setSaving(true);
    setError(null);
    try {
      setAssessment(await submitCgaAnswer(assessment, assessment.next_question.id, score));
    } catch {
      setError("这道题没有保存成功。请重试；如网络较慢，请先等待当前结果出现。");
    } finally {
      setSaving(false);
    }
  };

  const finish = async () => {
    if (!assessment || saving) return;
    setSaving(true);
    setError(null);
    try {
      const completed = await completeCgaAssessment(assessment);
      setAssessment(completed);
      setReport(await getCgaReport(completed.assessment_id));
    } catch {
      setError("结果尚未生成。请重试；您的已答内容仍会保留。");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    localStorage.removeItem(ACTIVE_ASSESSMENT_KEY);
    setAssessment(null);
    setReport(null);
    void load(true);
  };

  const textClass = seniorMode ? "text-lg" : "text-sm";
  const actionClass = seniorMode ? "min-h-12 text-lg" : "min-h-10 text-sm";

  return (
    <section className="mx-auto w-full max-w-2xl px-4 py-6" aria-live="polite">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h2 className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>PHQ-9 情绪筛查</h2>
          <p className={cn("mt-2 text-muted-foreground", textClass)}>
            请按过去两周的实际情况选择。筛查结果不能替代医生诊断。
          </p>
        </div>
        <Button variant="outline" onClick={onExit} className={actionClass}>退出评估</Button>
      </div>

      {error && (
        <div className={cn("mb-4 rounded-lg border border-destructive/40 bg-destructive/10 p-4", textClass)} role="alert">
          <p>{error}</p>
          <Button className={cn("mt-3", actionClass)} variant="outline" onClick={() => void load()} disabled={saving}>
            <RefreshCw className="mr-2 size-4" />重新连接
          </Button>
        </div>
      )}

      {!assessment && !error && <p className={cn("rounded-lg border p-5 text-muted-foreground", textClass)}>正在准备评估…</p>}

      {assessment?.risk.requires_immediate_safety_assessment && (
        <div className={cn("mb-4 rounded-lg border-2 border-destructive bg-destructive/10 p-4", textClass)} role="alert">
          <div className="flex gap-2 font-semibold"><AlertTriangle className="mt-0.5 size-5 shrink-0" />请立即寻求帮助</div>
          {assessment.risk.messages.map((message) => <p className="mt-2" key={message}>{message}</p>)}
        </div>
      )}

      {assessment?.next_question && (
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <p className={cn("text-muted-foreground", textClass)}>第 {assessment.next_question.position} / 9 题</p>
          {assessment.next_question.sensitive_prefix && <p className={cn("mt-3 text-amber-800 dark:text-amber-200", textClass)}>{assessment.next_question.sensitive_prefix}</p>}
          <h3 className={cn("mt-3 font-medium leading-relaxed", seniorMode ? "text-xl" : "text-lg")}>{assessment.next_question.text}</h3>
          <div className="mt-5 grid gap-3">
            {assessment.next_question.options.map(([value, label]) => (
              <Button key={value} variant="outline" className={cn("h-auto justify-start whitespace-normal px-5 py-4 text-left", actionClass)} onClick={() => void choose(value)} disabled={saving}>
                {label}
              </Button>
            ))}
          </div>
          {saving && <p className={cn("mt-3 text-muted-foreground", textClass)}>正在保存这一题…</p>}
        </div>
      )}

      {assessment && !assessment.next_question && assessment.status === "active" && (
        <div className="rounded-xl border bg-card p-5 text-center">
          <CheckCircle2 className="mx-auto size-10 text-primary" />
          <p className={cn("mt-3", textClass)}>九道题都已保存，可以查看筛查结果。</p>
          <Button className={cn("mt-4", actionClass)} onClick={() => void finish()} disabled={saving}>查看筛查结果</Button>
        </div>
      )}

      {report && (
        <div className="rounded-xl border bg-card p-5">
          <h3 className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>筛查结果</h3>
          <p className={cn("mt-4", textClass)}>得分：<strong>{report.total_score} / 27</strong></p>
          <p className={cn("mt-2", textClass)}>分级：{report.severity}</p>
          {report.safety_messages.map((message) => <p className={cn("mt-3", textClass)} key={message}>{message}</p>)}
          <p className={cn("mt-5 rounded-md bg-muted p-3 text-muted-foreground", textClass)}>{report.disclaimer}</p>
          <Button className={cn("mt-4", actionClass)} variant="outline" onClick={reset}>开始新的评估</Button>
        </div>
      )}
    </section>
  );
}
