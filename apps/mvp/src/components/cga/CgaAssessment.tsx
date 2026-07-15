"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardList, Download, RefreshCw } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { exportToMarkdown } from "@/lib/export";
import { useAppStore } from "@/stores/appStore";
import {
  completeCgaAssessment,
  getCgaAssessment,
  listCgaHistory,
  getCgaReport,
  listCgaScales,
  startCgaAssessment,
  submitCgaAnswer,
} from "@/services/gerclaw/cga";
import { GerclawApiError } from "@/services/gerclaw/client";
import type { CgaAssessment as Assessment, CgaHistoryItem, CgaReport, CgaScale, CgaScaleId } from "@/services/gerclaw/schemas";

interface CgaAssessmentProps {
  onExit: () => void;
}

const SEVERITY_LABEL: Record<CgaReport["severity"], string> = {
  none: "无明显症状",
  minimal: "轻微",
  mild: "轻度",
  moderate: "中度",
  moderately_severe: "中重度",
  severe: "重度",
  good: "睡眠质量很好",
  fair: "睡眠质量较好",
  average: "睡眠质量一般",
  poor: "睡眠质量差",
};

const COMPONENT_LABEL: Record<string, string> = {
  sleep_quality: "睡眠质量",
  sleep_latency: "入睡时间",
  sleep_duration: "睡眠时间",
  sleep_efficiency: "睡眠效率",
  sleep_disturbance: "睡眠障碍",
  hypnotic_medication: "催眠药物",
  daytime_dysfunction: "日间功能障碍",
};

function assessmentKey(scaleId: CgaScaleId) {
  return `gerclaw:cga:${scaleId}:assessment`;
}

const storedAssessmentIdSchema = z.string().uuid();

function buildReportExportContent(report: CgaReport): string {
  const lines = [
    "## 筛查结果",
    "",
    `- 得分：${report.total_score} / ${report.score_max}`,
    ...(report.raw_score !== null && report.standard_score !== null
      ? [`- 粗分：${report.raw_score}`, `- 标准分：${report.standard_score}`]
      : []),
    `- 分级：${SEVERITY_LABEL[report.severity]}`,
  ];
  if (Object.keys(report.component_scores).length > 0) {
    lines.push("", "## 各项得分", "");
    for (const [key, score] of Object.entries(report.component_scores)) {
      lines.push(`- ${COMPONENT_LABEL[key] ?? key}：${score} / 3`);
    }
  }
  if (report.safety_messages.length > 0) {
    lines.push("", "## 安全提示", "", ...report.safety_messages.map((message) => `- ${message}`));
  }
  lines.push("", "## 筛查说明", "", report.disclaimer);
  return lines.join("\n");
}

export function CgaAssessment({ onExit }: CgaAssessmentProps) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const [scales, setScales] = useState<CgaScale[]>([]);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [report, setReport] = useState<CgaReport | null>(null);
  const [history, setHistory] = useState<CgaHistoryItem[]>([]);
  const [selectedScaleId, setSelectedScaleId] = useState<CgaScaleId | null>(null);
  const [loadingDirectory, setLoadingDirectory] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [manualInput, setManualInput] = useState("");

  const selectedScale = useMemo(
    () => scales.find((scale) => scale.id === selectedScaleId) ?? null,
    [scales, selectedScaleId]
  );
  const textClass = seniorMode ? "text-lg" : "text-sm";
  const actionClass = seniorMode ? "min-h-12 text-lg" : "min-h-10 text-sm";

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    setHistoryError(null);
    try {
      setHistory((await listCgaHistory()).items);
    } catch {
      setHistoryError("历史筛查记录暂时无法读取，请稍后重试。");
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  const loadDirectory = useCallback(async () => {
    setLoadingDirectory(true);
    setError(null);
    void loadHistory();
    try {
      setScales((await listCgaScales()).scales);
    } catch {
      setError("评估目录暂时无法连接。请检查网络后重试。");
    } finally {
      setLoadingDirectory(false);
    }
  }, [loadHistory]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadDirectory(), 0);
    return () => window.clearTimeout(timer);
  }, [loadDirectory]);

  const begin = useCallback(async (scale: CgaScale) => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const key = assessmentKey(scale.id);
      const storedId = localStorage.getItem(key);
      let next: Assessment | null = null;
      const parsedStoredId = storedAssessmentIdSchema.safeParse(storedId);
      if (storedId !== null && !parsedStoredId.success) {
        localStorage.removeItem(key);
        setNotice("上次评估记录格式无效，已为您开始一份新的评估。");
      }
      if (parsedStoredId.success) {
        try {
          next = await getCgaAssessment(parsedStoredId.data);
          if (next.scale_id !== scale.id) {
            throw new GerclawApiError("评估量表不匹配", "CGA_NOT_FOUND", 404);
          }
        } catch (caught) {
          if (!(caught instanceof GerclawApiError) || caught.code !== "CGA_NOT_FOUND") throw caught;
          localStorage.removeItem(key);
          setNotice("上次评估记录已无法恢复，已为您开始一份新的评估。");
        }
      }
      if (!next) next = await startCgaAssessment(scale.id);
      localStorage.setItem(key, next.assessment_id);
      setSelectedScaleId(scale.id);
      setAssessment(next);
      setReport(next.status === "completed" ? await getCgaReport(next.assessment_id) : null);
    } catch {
      setError("评估服务暂时不可用。请检查网络后重试，已有进度不会被清除。");
    } finally {
      setSaving(false);
    }
  }, []);

  const openHistory = async (historyItem: CgaHistoryItem) => {
    const scale = scales.find((item) => item.id === historyItem.scale_id);
    if (!scale || saving) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const historicAssessment = await getCgaAssessment(historyItem.assessment_id);
      if (
        historicAssessment.status !== "completed" ||
        historicAssessment.scale_id !== historyItem.scale_id
      ) {
        throw new GerclawApiError("历史记录状态不正确", "CGA_HISTORY_INVALID", 409);
      }
      setSelectedScaleId(scale.id);
      setAssessment(historicAssessment);
      setReport(await getCgaReport(historicAssessment.assessment_id));
    } catch {
      setError("这份历史筛查报告暂时无法读取，请稍后重试。");
    } finally {
      setSaving(false);
    }
  };

  const choose = async (score: number) => {
    if (!assessment?.next_question || saving) return;
    setSaving(true);
    setError(null);
    try {
      setAssessment(await submitCgaAnswer(assessment, assessment.next_question.id, score));
      setManualInput("");
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
    if (!selectedScale) return;
    localStorage.removeItem(assessmentKey(selectedScale.id));
    setAssessment(null);
    setReport(null);
    void begin(selectedScale);
  };

  const exportReport = () => {
    if (!report || !selectedScale) return;
    exportToMarkdown({
      title: `${selectedScale.name}筛查报告`,
      subtitle: "结果由服务端确定性规则生成",
      content: buildReportExportContent(report),
    });
    setNotice("筛查报告已导出为 Markdown 文件。报告仅供筛查参考，不能替代医生诊断。");
  };

  const backToDirectory = () => {
    setAssessment(null);
    setReport(null);
    setSelectedScaleId(null);
    setError(null);
    setNotice(null);
    setManualInput("");
    void loadHistory();
  };

  const submitManualAnswer = () => {
    const question = assessment?.next_question;
    if (!question || saving) return;
    if (question.input_kind === "clock_minutes") {
      const matched = /^(\d{2}):(\d{2})$/.exec(manualInput);
      if (!matched) {
        setError("请选择有效的时间后再保存。");
        return;
      }
      const hours = Number(matched[1]);
      const minutes = Number(matched[2]);
      if (hours > 23 || minutes > 59) {
        setError("请选择有效的时间后再保存。");
        return;
      }
      void choose(hours * 60 + minutes);
      return;
    }
    const duration = Number(manualInput);
    if (!Number.isInteger(duration) || duration < 1 || duration > 1_439) {
      setError("请输入 1 到 1439 分钟之间的实际睡眠时长。");
      return;
    }
    void choose(duration);
  };

  return (
    <section className="mx-auto w-full max-w-2xl px-4 py-6" aria-live="polite">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h2 className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>老年综合评估</h2>
          <p className={cn("mt-2 text-muted-foreground", textClass)}>选择一项筛查量表，答案会安全保存，之后可以继续作答。</p>
        </div>
        <Button variant="outline" onClick={onExit} className={actionClass}>退出评估</Button>
      </div>

      {error && (
        <div className={cn("mb-4 rounded-lg border border-destructive/40 bg-destructive/10 p-4", textClass)} role="alert">
          <p>{error}</p>
          <Button className={cn("mt-3", actionClass)} variant="outline" onClick={() => void (assessment ? begin(selectedScale!) : loadDirectory())} disabled={saving || loadingDirectory}>
            <RefreshCw className="mr-2 size-4" />重新连接
          </Button>
        </div>
      )}

      {notice && <p className={cn("mb-4 rounded-lg border bg-muted p-4", textClass)}>{notice}</p>}

      {!assessment && !error && (
        <div className="space-y-6">
          {loadingDirectory ? (
            <p className={cn("rounded-lg border p-5 text-muted-foreground", textClass)}>正在准备评估项目…</p>
          ) : scales.map((scale) => (
            <article key={scale.id} className="rounded-xl border bg-card p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-full bg-primary/10 p-2 text-primary"><ClipboardList className="size-5" /></div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className={cn("font-semibold", seniorMode ? "text-xl" : "text-lg")}>{scale.name} 筛查</h3>
                    <span className={cn("text-muted-foreground", textClass)}>{scale.question_count} 题</span>
                  </div>
                  <p className={cn("mt-2 text-muted-foreground", textClass)}>{scale.description}</p>
                  <Button className={cn("mt-4", actionClass)} onClick={() => void begin(scale)} disabled={saving}>
                    开始 {scale.name} 筛查
                  </Button>
                </div>
              </div>
            </article>
          ))}
          <section aria-labelledby="cga-history-title" className="border-t pt-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 id="cga-history-title" className={cn("font-semibold", seniorMode ? "text-xl" : "text-lg")}>我的历史筛查结果</h3>
              <span className={cn("text-muted-foreground", textClass)}>仅显示最近 10 份已完成报告</span>
            </div>
            {loadingHistory ? (
              <p className={cn("mt-3 rounded-lg border p-4 text-muted-foreground", textClass)}>正在读取历史筛查结果…</p>
            ) : historyError ? (
              <div className={cn("mt-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4", textClass)} role="alert">
                <p>{historyError}</p>
                <Button className={cn("mt-3", actionClass)} variant="outline" onClick={() => void loadHistory()} disabled={saving}>重新读取历史记录</Button>
              </div>
            ) : history.length === 0 ? (
              <p className={cn("mt-3 rounded-lg border p-4 text-muted-foreground", textClass)}>尚无已完成的筛查报告。完成一项筛查后，结果会显示在这里。</p>
            ) : (
              <div className="mt-3 space-y-3">
                {history.map((historyItem) => {
                  const scale = scales.find((item) => item.id === historyItem.scale_id);
                  return (
                    <article key={historyItem.assessment_id} className="rounded-xl border bg-card p-4 shadow-sm">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h4 className={cn("font-semibold", seniorMode ? "text-lg" : "text-base")}>{scale?.name ?? historyItem.scale_id.toUpperCase()} 筛查</h4>
                          <p className={cn("mt-1 text-muted-foreground", textClass)}>完成于 {new Date(historyItem.completed_at).toLocaleString("zh-CN")}</p>
                          <p className={cn("mt-2", textClass)}>得分：<strong>{historyItem.report.total_score} / {historyItem.report.score_max}</strong>；分级：{SEVERITY_LABEL[historyItem.report.severity]}</p>
                          {historyItem.report.requires_immediate_safety_assessment && (
                            <p className={cn("mt-2 flex items-start gap-2 font-medium text-destructive", textClass)}><AlertTriangle className="mt-0.5 size-5 shrink-0" />该报告包含需立即安全评估的提示，请及时寻求帮助。</p>
                          )}
                        </div>
                        <Button className={actionClass} variant="outline" onClick={() => void openHistory(historyItem)} disabled={saving}>查看报告</Button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}

      {assessment && selectedScale && (
        <>
          <Button variant="ghost" className={cn("mb-4 px-0", actionClass)} onClick={backToDirectory} disabled={saving}>
            <ArrowLeft className="mr-2 size-4" />返回量表选择
          </Button>
          <div className="mb-4">
            <h3 className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>{selectedScale.name} 筛查</h3>
            <p className={cn("mt-2 text-muted-foreground", textClass)}>{selectedScale.description}。筛查结果不能替代医生诊断。</p>
          </div>

          {assessment.risk.requires_immediate_safety_assessment && (
            <div className={cn("mb-4 rounded-lg border-2 border-destructive bg-destructive/10 p-4", textClass)} role="alert">
              <div className="flex gap-2 font-semibold"><AlertTriangle className="mt-0.5 size-5 shrink-0" />请立即寻求帮助</div>
              {assessment.risk.messages.map((message) => <p className="mt-2" key={message}>{message}</p>)}
            </div>
          )}

          {assessment.next_question && (
            <div className="rounded-xl border bg-card p-4 shadow-sm">
              <p className={cn("text-muted-foreground", textClass)}>第 {assessment.next_question.position} / {selectedScale.question_count} 题</p>
              {assessment.next_question.sensitive_prefix && <p className={cn("mt-3 text-amber-800 dark:text-amber-200", textClass)}>{assessment.next_question.sensitive_prefix}</p>}
              <h4 className={cn("mt-3 font-medium leading-relaxed", seniorMode ? "text-xl" : "text-lg")}>{assessment.next_question.text}</h4>
              {assessment.next_question.input_kind === "ordinal" ? (
                <div className="mt-5 grid gap-3">
                  {assessment.next_question.options.map(([value, label]) => (
                    <Button key={value} variant="outline" className={cn("h-auto justify-start whitespace-normal px-5 py-4 text-left", actionClass)} onClick={() => void choose(value)} disabled={saving}>{label}</Button>
                  ))}
                </div>
              ) : (
                <div className="mt-5 space-y-3">
                  <label className={cn("block font-medium", textClass)} htmlFor={`cga-${assessment.next_question.id}`}>
                    {assessment.next_question.input_kind === "clock_minutes" ? "选择时间" : "填写分钟数"}
                  </label>
                  <input
                    id={`cga-${assessment.next_question.id}`}
                    key={assessment.next_question.id}
                    type={assessment.next_question.input_kind === "clock_minutes" ? "time" : "number"}
                    min={assessment.next_question.input_kind === "duration_minutes" ? 1 : undefined}
                    max={assessment.next_question.input_kind === "duration_minutes" ? 1439 : undefined}
                    step={assessment.next_question.input_kind === "duration_minutes" ? 1 : undefined}
                    value={manualInput}
                    onChange={(event) => setManualInput(event.target.value)}
                    disabled={saving}
                    className={cn("w-full rounded-md border bg-background px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-ring", actionClass)}
                    aria-describedby={`cga-${assessment.next_question.id}-help`}
                  />
                  <p id={`cga-${assessment.next_question.id}-help`} className={cn("text-muted-foreground", textClass)}>
                    {assessment.next_question.input_kind === "clock_minutes" ? "请按最近一个月的通常时间填写。" : "请填写每晚实际睡眠的分钟数，例如 480 表示 8 小时。"}
                  </p>
                  <Button className={actionClass} onClick={submitManualAnswer} disabled={saving || manualInput.length === 0}>保存这一题</Button>
                </div>
              )}
              {saving && <p className={cn("mt-3 text-muted-foreground", textClass)}>正在保存这一题…</p>}
            </div>
          )}

          {assessment.status === "active" && !assessment.next_question && (
            <div className="rounded-xl border bg-card p-5 text-center">
              <CheckCircle2 className="mx-auto size-10 text-primary" />
              <p className={cn("mt-3", textClass)}>所有题目都已保存，可以查看筛查结果。</p>
              <Button className={cn("mt-4", actionClass)} onClick={() => void finish()} disabled={saving}>查看筛查结果</Button>
            </div>
          )}

          {report && (
            <div className="rounded-xl border bg-card p-5">
              <h4 className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>筛查结果</h4>
              <p className={cn("mt-4", textClass)}>得分：<strong>{report.total_score} / {report.score_max}</strong></p>
              {report.raw_score !== null && report.standard_score !== null && <p className={cn("mt-2", textClass)}>粗分：{report.raw_score}；标准分：{report.standard_score}</p>}
              <p className={cn("mt-2", textClass)}>分级：{SEVERITY_LABEL[report.severity]}</p>
              {Object.keys(report.component_scores).length > 0 && (
                <div className={cn("mt-4 rounded-md bg-muted p-3", textClass)}>
                  <p className="font-medium">各项得分</p>
                  <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {Object.entries(report.component_scores).map(([key, score]) => (
                      <div className="flex justify-between gap-3" key={key}>
                        <dt>{COMPONENT_LABEL[key] ?? key}</dt>
                        <dd>{score} / 3</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
              {report.safety_messages.map((message) => <p className={cn("mt-3", textClass)} key={message}>{message}</p>)}
              <p className={cn("mt-5 rounded-md bg-muted p-3 text-muted-foreground", textClass)}>{report.disclaimer}</p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Button className={actionClass} variant="outline" onClick={exportReport}>
                  <Download className="mr-2 size-4" />导出筛查报告
                </Button>
                <Button className={actionClass} variant="outline" onClick={reset}>重新开始此量表</Button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
