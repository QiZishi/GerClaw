"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardList, Download, FileText, FileType, Pause, RefreshCw, Square, Volume2 } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import { exportToDocx, exportToMarkdown, exportToPdf } from "@/lib/export";
import { recordedCgaOptionAudio, recordedCgaQuestionAudio } from "@/lib/cga-audio";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { useAppStore } from "@/stores/appStore";
import { toast } from "@/components/ui/toast";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  completeCgaAssessment,
  getCgaAssessment,
  getCgaComparison,
  listActiveCgaAssessments,
  listCgaHistory,
  getCgaReport,
  listCgaScales,
  startCgaAssessment,
  submitCgaAnswer,
} from "@/services/gerclaw/cga";
import { GerclawApiError } from "@/services/gerclaw/client";
import type { CgaAssessment as Assessment, CgaComparison, CgaHistoryItem, CgaQuestion, CgaReport, CgaScale, CgaScaleId } from "@/services/gerclaw/schemas";

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
  screen_negative: "本次筛查未提示明显问题",
  possible_impairment: "建议进一步核验",
  normal: "本次筛查未提示明显问题",
  mild_impairment: "建议进一步核验",
  moderate_impairment: "建议尽快进一步评估",
  severe_impairment: "建议尽快进一步评估",
};

const COMPONENT_LABEL: Record<string, string> = {
  sleep_quality: "睡眠质量",
  sleep_latency: "入睡时间",
  sleep_duration: "睡眠时间",
  sleep_efficiency: "睡眠效率",
  sleep_disturbance: "睡眠障碍",
  hypnotic_medication: "催眠药物",
  daytime_dysfunction: "日间功能障碍",
  word_recall: "三词回忆",
  clock_task_self_report: "时钟任务(本人作答)",
  orientation: "定向力",
  immediate_memory: "即时记忆",
  attention_calculation: "注意力和计算",
  recall: "回忆能力",
  language_and_tasks: "语言和任务",
};

const COMPONENT_MAX: Record<string, number> = {
  word_recall: 3,
  clock_task_self_report: 2,
  orientation: 10,
  immediate_memory: 3,
  attention_calculation: 5,
  recall: 3,
  language_and_tasks: 9,
};

function assessmentKey(scaleId: CgaScaleId) {
  return `gerclaw:cga:${scaleId}:assessment`;
}

function buildQuestionSpeechText(question: CgaQuestion): string {
  const parts = [question.sensitive_prefix, question.text];
  if (question.options.length > 0) {
    parts.push("可选择的答案有", ...question.options.map(([, label]) => label));
  }
  return parts.filter(Boolean).join("。") + "。";
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
      lines.push(`- ${COMPONENT_LABEL[key] ?? key}：${score} / ${COMPONENT_MAX[key] ?? 3}`);
    }
  }
  if (report.safety_messages.length > 0) {
    lines.push("", "## 安全提示", "", ...report.safety_messages.map((message) => `- ${message}`));
  }
  lines.push("", "## 筛查说明", "", report.disclaimer);
  lines.push(
    "",
    "## 医疗免责声明",
    "",
    "本筛查信息仅供参考，不能替代专业医生的诊断和治疗建议。如有不适请及时就医。"
  );
  return lines.join("\n");
}

function buildCgaExportTitle(scaleName: string): string {
  const now = new Date();
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  return `GerClaw_${scaleName}筛查报告_${date}`;
}

export function CgaAssessment({ onExit }: CgaAssessmentProps) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const autoTtsPlayback = useAppStore((state) => state.autoTtsPlayback);
  const [scales, setScales] = useState<CgaScale[]>([]);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [savedAssessments, setSavedAssessments] = useState<Partial<Record<CgaScaleId, Assessment>>>({});
  const [report, setReport] = useState<CgaReport | null>(null);
  const [comparison, setComparison] = useState<CgaComparison | null>(null);
  const [history, setHistory] = useState<CgaHistoryItem[]>([]);
  const [selectedScaleId, setSelectedScaleId] = useState<CgaScaleId | null>(null);
  const [loadingDirectory, setLoadingDirectory] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [manualInput, setManualInput] = useState("");
  const [selectedOrdinalScore, setSelectedOrdinalScore] = useState<number | null>(null);
  const [supplementalDetail, setSupplementalDetail] = useState("");
  const [exportingFormat, setExportingFormat] = useState<"markdown" | "docx" | "pdf" | null>(null);
  const autoReadQuestionKeyRef = useRef<string | null>(null);
  const reportExportRef = useRef<HTMLDivElement | null>(null);
  const {
    isPlaying: isQuestionPlaying,
    isPaused: isQuestionPaused,
    isLoading: isQuestionAudioLoading,
    progress: questionAudioProgress,
    play: playQuestion,
    playSource: playQuestionSource,
    pause: pauseQuestion,
    resume: resumeQuestion,
    stop: stopQuestion,
  } = useAudioPlayer();

  const selectedScale = useMemo(
    () => scales.find((scale) => scale.id === selectedScaleId) ?? null,
    [scales, selectedScaleId]
  );
  const textClass = seniorMode ? "text-lg" : "text-sm";
  const actionClass = seniorMode ? "min-h-12 text-lg" : "min-h-10 text-sm";
  const exitLabel = assessment?.status === "active" ? "休息，稍后继续" : "退出评估";

  useEffect(() => {
    // An answer changes the active question; continuing the old question would
    // make the controls lie about what is currently being read aloud.
    stopQuestion();
  }, [assessment?.next_question?.id, stopQuestion]);

  const startQuestionAudio = useCallback(() => {
    if (!assessment?.next_question) return;
    const source = recordedCgaQuestionAudio(
      assessment.scale_id,
      assessment.definition_version,
      assessment.next_question
    );
    const playback = source
      ? playQuestionSource(source)
      : playQuestion(buildQuestionSpeechText(assessment.next_question));
    void playback.catch(() => {
      toast.show("题目朗读暂时不可用，请改用文字阅读后重试");
    });
  }, [assessment, playQuestion, playQuestionSource]);

  const startOptionAudio = useCallback((optionOrdinal: number, label: string) => {
    if (!assessment?.next_question) return;
    const source = recordedCgaOptionAudio(
      assessment.scale_id,
      assessment.definition_version,
      assessment.next_question,
      optionOrdinal
    );
    const playback = source ? playQuestionSource(source) : playQuestion(label);
    void playback.catch(() => {
      toast.show("选项朗读暂时不可用，请改用文字阅读后重试");
    });
  }, [assessment, playQuestion, playQuestionSource]);

  const resumeQuestionAudio = () => {
    void resumeQuestion().catch(() => {
      toast.show("无法继续朗读，请从头重新播放");
    });
  };

  useEffect(() => {
    const question = assessment?.next_question;
    if (!seniorMode || !autoTtsPlayback || !assessment || !question) return;

    // React development mode can run effects twice.  Keep one attempt per
    // concrete assessment/question pair, while allowing a restarted
    // assessment to read its first question again.
    const questionKey = `${assessment.assessment_id}:${question.id}`;
    if (autoReadQuestionKeyRef.current === questionKey) return;
    autoReadQuestionKeyRef.current = questionKey;

    startQuestionAudio();
  }, [assessment, autoTtsPlayback, seniorMode, startQuestionAudio]);

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

  const loadSavedAssessments = useCallback(async (availableScales: CgaScale[]) => {
    const fromServer = (await listActiveCgaAssessments()).items;
    const savedByScale: Partial<Record<CgaScaleId, Assessment>> = {};
    for (const item of fromServer) {
      if (!savedByScale[item.scale_id]) {
        savedByScale[item.scale_id] = item;
        localStorage.setItem(assessmentKey(item.scale_id), item.assessment_id);
      }
    }
    const saved = await Promise.all(availableScales.map(async (scale) => {
      if (savedByScale[scale.id]) return null;
      const storedId = localStorage.getItem(assessmentKey(scale.id));
      const parsedStoredId = storedAssessmentIdSchema.safeParse(storedId);
      if (!parsedStoredId.success) return null;
      try {
        const existing = await getCgaAssessment(parsedStoredId.data);
        return existing.scale_id === scale.id ? existing : null;
      } catch (caught) {
        if (caught instanceof GerclawApiError && caught.code === "CGA_NOT_FOUND") {
          localStorage.removeItem(assessmentKey(scale.id));
        }
        return null;
      }
    }));
    const next: Partial<Record<CgaScaleId, Assessment>> = { ...savedByScale };
    for (const item of saved) {
      if (item) next[item.scale_id] = item;
    }
    setSavedAssessments(next);
  }, []);

  const loadDirectory = useCallback(async () => {
    setLoadingDirectory(true);
    setError(null);
    void loadHistory();
    try {
      const availableScales = (await listCgaScales()).scales;
      setScales(availableScales);
      await loadSavedAssessments(availableScales);
    } catch {
      setError("评估目录暂时无法连接。请检查网络后重试。");
    } finally {
      setLoadingDirectory(false);
    }
  }, [loadHistory, loadSavedAssessments]);

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
      setSavedAssessments((current) => ({ ...current, [scale.id]: next! }));
      setSelectedScaleId(scale.id);
      setAssessment(next);
      if (next.status === "completed") {
        setReport(await getCgaReport(next.assessment_id));
        try {
          setComparison(await getCgaComparison(next.assessment_id));
        } catch {
          // The completed report remains usable if its optional historical
          // comparison read is temporarily unavailable.
          setComparison(null);
        }
      } else {
        setReport(null);
        setComparison(null);
      }
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
      try {
        setComparison(await getCgaComparison(historicAssessment.assessment_id));
      } catch {
        setComparison(null);
      }
    } catch {
      setError("这份历史筛查报告暂时无法读取，请稍后重试。");
    } finally {
      setSaving(false);
    }
  };

  const choose = async (score: number, detail?: string) => {
    if (!assessment?.next_question || saving) return;
    setSaving(true);
    setError(null);
    try {
      setAssessment(await submitCgaAnswer(assessment, assessment.next_question.id, score, detail));
      setManualInput("");
      setSelectedOrdinalScore(null);
      setSupplementalDetail("");
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
      setSavedAssessments((current) => ({ ...current, [completed.scale_id]: completed }));
      setReport(await getCgaReport(completed.assessment_id));
      try {
        setComparison(await getCgaComparison(completed.assessment_id));
      } catch {
        setComparison(null);
      }
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
    setComparison(null);
    setManualInput("");
    setSelectedOrdinalScore(null);
    setSupplementalDetail("");
    void begin(selectedScale);
  };

  const exportReport = async (format: "markdown" | "docx" | "pdf") => {
    if (!report || !selectedScale) return;
    setExportingFormat(format);
    const title = buildCgaExportTitle(selectedScale.name);
    const content = buildReportExportContent(report);
    try {
      if (format === "markdown") {
        exportToMarkdown({ title, subtitle: "结果由服务端确定性规则生成", content });
      } else if (format === "docx") {
        await exportToDocx(title, content, "结果由服务端确定性规则生成");
      } else {
        if (!reportExportRef.current) throw new Error("CGA report is not ready for PDF export");
        await exportToPdf(reportExportRef.current, title);
      }
      setNotice(`筛查报告已导出为${format === "markdown" ? " Markdown" : format === "docx" ? " Word" : " PDF"} 文件。报告仅供筛查参考，不能替代医生诊断。`);
    } catch {
      toast.show("导出暂时失败，请重试或改用其他格式。");
    } finally {
      setExportingFormat(null);
    }
  };

  const backToDirectory = () => {
    setAssessment(null);
    setReport(null);
    setComparison(null);
    setSelectedScaleId(null);
    setError(null);
    setNotice(null);
    setManualInput("");
    setSelectedOrdinalScore(null);
    setSupplementalDetail("");
    void loadDirectory();
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

  const isPsqiSupplementalQuestion = assessment?.next_question?.id === "psqi_5j";

  return (
    <section className="mx-auto w-full max-w-2xl px-4 pb-6 pt-16 sm:py-6" aria-live="polite">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h2 className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>老年综合评估</h2>
          <p className={cn("mt-2 text-muted-foreground", textClass)}>选择一项筛查量表；答案会自动保存，可稍后继续。</p>
        </div>
        <Button variant="outline" onClick={onExit} className={actionClass}>{exitLabel}</Button>
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
            <InlineLoadingState
              message="正在准备评估项目"
              className={cn("min-h-28 rounded-lg border px-5", textClass)}
            />
          ) : scales.map((scale) => {
            const savedAssessment = savedAssessments[scale.id];
            const actionVerb = savedAssessment?.status === "active"
              ? "继续"
              : savedAssessment?.status === "completed"
                ? "查看"
                : "开始";
            const actionLabel = `${actionVerb} ${scale.name} 筛查`;
            return (
            <article key={scale.id} className="rounded-xl border bg-card p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-full bg-primary/10 p-2 text-primary"><ClipboardList className="size-5" /></div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className={cn("font-semibold", seniorMode ? "text-xl" : "text-lg")}>{scale.name} 筛查</h3>
                    <span className={cn("text-muted-foreground", textClass)}>{scale.question_count} 题</span>
                  </div>
                  <p className={cn("mt-2 text-muted-foreground", textClass)}>{scale.description}</p>
                  {savedAssessment?.status === "active" && (
                    <p className={cn("mt-3 font-medium text-primary", textClass)}>已保存进度，可从第 {savedAssessment.next_question?.position ?? savedAssessment.answered_count + 1} 题继续。</p>
                  )}
                  <Button className={cn("mt-4", actionClass)} onClick={() => void begin(scale)} disabled={saving}>
                    {actionLabel}
                  </Button>
                </div>
              </div>
            </article>
            );
          })}
          <section aria-labelledby="cga-history-title" className="border-t pt-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 id="cga-history-title" className={cn("font-semibold", seniorMode ? "text-xl" : "text-lg")}>我的历史筛查结果</h3>
              <span className={cn("text-muted-foreground", textClass)}>仅显示最近 10 份已完成报告</span>
            </div>
            {loadingHistory ? (
              <InlineLoadingState
                message="正在读取历史筛查结果"
                className={cn("mt-3 min-h-20 rounded-lg border px-4", textClass)}
              />
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
              <div className="space-y-2">
                <p className={cn("text-muted-foreground", textClass)}>第 {assessment.next_question.position} / {selectedScale.question_count} 题</p>
                <div
                  className="h-2 overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  aria-label="评估完成进度"
                  aria-valuemin={0}
                  aria-valuemax={selectedScale.question_count}
                  aria-valuenow={assessment.answered_count}
                  aria-valuetext={`已完成 ${assessment.answered_count} / ${selectedScale.question_count} 题`}
                >
                  <div
                    className="h-full origin-left rounded-full bg-primary transition-transform duration-200 ease-[var(--motion-ease-out)] motion-reduce:transition-none"
                    style={{ transform: `scaleX(${Math.min(1, assessment.answered_count / selectedScale.question_count)})` }}
                  />
                </div>
              </div>
              {assessment.next_question.sensitive_prefix && <p className={cn("mt-3 text-amber-800 dark:text-amber-200", textClass)}>{assessment.next_question.sensitive_prefix}</p>}
              <h4 className={cn("mt-3 font-medium leading-relaxed", seniorMode ? "text-xl" : "text-lg")}>{assessment.next_question.text}</h4>
              <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label="题目朗读控制">
                {isQuestionAudioLoading ? (
                  <Button variant="outline" className={cn("gap-2", actionClass)} onClick={stopQuestion}>
                    <Volume2 className="size-4" />正在准备，点击取消
                  </Button>
                ) : isQuestionPlaying || isQuestionPaused ? (
                  <>
                    <Button
                      variant="outline"
                      className={cn("gap-2", actionClass)}
                      onClick={isQuestionPlaying ? pauseQuestion : resumeQuestionAudio}
                    >
                      {isQuestionPlaying ? <Pause className="size-4" /> : <Volume2 className="size-4" />}
                      {isQuestionPlaying ? "暂停朗读" : "继续朗读"}
                    </Button>
                    <Button variant="outline" className={cn("gap-2", actionClass)} onClick={stopQuestion}>
                      <Square className="size-4" />停止朗读
                    </Button>
                    <div
                      className="h-1.5 w-24 overflow-hidden rounded-full bg-muted"
                      role="progressbar"
                      aria-label="题目朗读进度"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(questionAudioProgress * 100)}
                    >
                      <div
                        className="h-full origin-left rounded-full bg-primary transition-transform duration-150 ease-[var(--motion-ease-out)] motion-reduce:transition-none"
                        style={{ transform: `scaleX(${Math.min(1, Math.max(0, questionAudioProgress))})` }}
                      />
                    </div>
                  </>
                ) : (
                  <Button variant="outline" className={cn("gap-2", actionClass)} onClick={startQuestionAudio}>
                    <Volume2 className="size-4" />朗读本题
                  </Button>
                )}
              </div>
              {assessment.next_question.input_kind === "ordinal" && !isPsqiSupplementalQuestion ? (
                <div className="mt-5 grid gap-3">
                  {assessment.next_question.options.map(([value, label], optionOrdinal) => (
                    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2" key={value}>
                      <Button variant="outline" className={cn("h-auto justify-start whitespace-normal px-5 py-4 text-left", actionClass)} onClick={() => void choose(value)} disabled={saving}>{label}</Button>
                      <Button
                        type="button"
                        variant="outline"
                        className={cn("min-h-11 gap-1.5 px-3", actionClass)}
                        onClick={() => startOptionAudio(optionOrdinal, label)}
                        disabled={saving}
                        aria-label={`朗读选项：${label}`}
                      >
                        <Volume2 className="size-4" />朗读
                      </Button>
                    </div>
                  ))}
                </div>
              ) : assessment.next_question.input_kind === "ordinal" ? (
                <div className="mt-5 space-y-4">
                  <div className="grid gap-3" role="radiogroup" aria-label="影响睡眠事情发生频率">
                    {assessment.next_question.options.map(([value, label], optionOrdinal) => (
                      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2" key={value}>
                        <Button
                          type="button"
                          variant={selectedOrdinalScore === value ? "default" : "outline"}
                          className={cn("h-auto justify-start whitespace-normal px-5 py-4 text-left", actionClass)}
                          onClick={() => setSelectedOrdinalScore(value)}
                          disabled={saving}
                          role="radio"
                          aria-checked={selectedOrdinalScore === value}
                        >
                          {label}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          className={cn("min-h-11 gap-1.5 px-3", actionClass)}
                          onClick={() => startOptionAudio(optionOrdinal, label)}
                          disabled={saving}
                          aria-label={`朗读选项：${label}`}
                        >
                          <Volume2 className="size-4" />朗读
                        </Button>
                      </div>
                    ))}
                  </div>
                  <div className="rounded-lg border border-sky-200 bg-sky-50 p-4 dark:border-sky-900/50 dark:bg-sky-950/20">
                    <label htmlFor="psqi-5j-detail" className={cn("block font-medium", textClass)}>
                      如有其他影响睡眠的事情，请简要说明（可不填）
                    </label>
                    <textarea
                      id="psqi-5j-detail"
                      value={supplementalDetail}
                      onChange={(event) => setSupplementalDetail(event.target.value)}
                      maxLength={500}
                      rows={3}
                      disabled={saving}
                      className={cn("mt-3 w-full resize-y rounded-md border bg-background px-4 py-3 leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-ring", textClass)}
                      aria-describedby="psqi-5j-detail-help"
                    />
                    <p id="psqi-5j-detail-help" className={cn("mt-2 text-muted-foreground", textClass)}>
                      这项说明不会参与分数计算，也不会显示在历史摘要或导出的筛查报告中。
                    </p>
                  </div>
                  <Button
                    className={actionClass}
                    onClick={() => selectedOrdinalScore !== null && void choose(selectedOrdinalScore, supplementalDetail)}
                    disabled={saving || selectedOrdinalScore === null}
                  >
                    保存这一题
                  </Button>
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
            <div ref={reportExportRef} className="rounded-xl border bg-card p-5">
              <h4 className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>筛查结果</h4>
              <p className={cn("mt-4", textClass)}>得分：<strong>{report.total_score} / {report.score_max}</strong></p>
              {report.raw_score !== null && report.standard_score !== null && <p className={cn("mt-2", textClass)}>粗分：{report.raw_score}；标准分：{report.standard_score}</p>}
              <p className={cn("mt-2", textClass)}>分级：{SEVERITY_LABEL[report.severity]}</p>
              {report.education_level !== null && report.education_threshold !== null && (
                <p className={cn("mt-2", textClass)}>
                  本次使用的教育程度分界值：{report.education_threshold} 分
                  {report.education_adjusted_screen_positive ? "；建议进一步评估。" : "。"}
                </p>
              )}
              {comparison && (
                <div className={cn("mt-4 rounded-md border bg-muted/50 p-3", textClass)}>
                  <p className="font-medium">与上一次同量表筛查的对照</p>
                  {comparison.status === "comparable" && comparison.prior && comparison.score_delta !== null ? (
                    <>
                      <p className="mt-2">本次与上次的分数差：<strong>{comparison.score_delta > 0 ? "+" : ""}{comparison.score_delta}</strong></p>
                      <p className="mt-2 text-muted-foreground">上次完成于 {new Date(comparison.prior.completed_at).toLocaleString("zh-CN")}。</p>
                    </>
                  ) : (
                    <p className="mt-2">{comparison.status === "definition_version_changed" ? "两次量表版本不同，未作分数对照。" : "暂无可对照的同量表历史结果。"}</p>
                  )}
                  <p className="mt-2 text-muted-foreground">{comparison.disclaimer}</p>
                </div>
              )}
              {Object.keys(report.component_scores).length > 0 && (
                <div className={cn("mt-4 rounded-md bg-muted p-3", textClass)}>
                  <p className="font-medium">各项得分</p>
                  <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {Object.entries(report.component_scores).map(([key, score]) => (
                      <div className="flex justify-between gap-3" key={key}>
                        <dt>{COMPONENT_LABEL[key] ?? key}</dt>
                        <dd>{score} / {COMPONENT_MAX[key] ?? 3}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
              {report.safety_messages.map((message) => <p className={cn("mt-3", textClass)} key={message}>{message}</p>)}
              <p className={cn("mt-5 rounded-md bg-muted p-3 text-muted-foreground", textClass)}>{report.disclaimer}</p>
              <div className="mt-4 flex flex-wrap gap-3" data-html2canvas-ignore>
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button className={actionClass} variant="outline" disabled={exportingFormat !== null}>
                        <Download className="mr-2 size-4" />
                        {exportingFormat ? "正在导出…" : "导出报告"}
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="start" className={cn(seniorMode && "min-w-56 text-base")}>
                    <DropdownMenuItem className={cn(seniorMode && "min-h-12")} onClick={() => void exportReport("pdf")}>
                      <FileText className="size-4" />PDF（便于打印）
                    </DropdownMenuItem>
                    <DropdownMenuItem className={cn(seniorMode && "min-h-12")} onClick={() => void exportReport("docx")}>
                      <FileType className="size-4" />Word（便于编辑）
                    </DropdownMenuItem>
                    <DropdownMenuItem className={cn(seniorMode && "min-h-12")} onClick={() => void exportReport("markdown")}>
                      <FileText className="size-4" />Markdown（便于保存）
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button className={actionClass} variant="outline" onClick={reset}>重新开始此量表</Button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
