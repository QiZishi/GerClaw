"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { RefreshCw, Square } from "lucide-react";
import { ChatInput, type ChatDocumentAttachment } from "@/components/chat/ChatInput";
import { Button } from "@/components/ui/button";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { PRESCRIPTION_COMPLETING_MAX_TURNS } from "@/lib/constants";
import {
  generatePrescriptionDraft,
  getClinicalIntake,
  listPrescriptionDrafts,
  processPrescriptionConversationTurn,
  startClinicalIntake,
  updateClinicalIntake,
} from "@/services/gerclaw/clinical-intakes";
import type { ClinicalIntake, FivePrescriptionDraft } from "@/services/gerclaw/schemas";
import type { ImageAttachment } from "@/types";
import { GerclawApiError } from "@/services/gerclaw/client";
import {
  prepareManualPrescriptionAnswers,
  prescriptionMissingFields,
  prescriptionTurnProgress,
} from "./prescription-completion";

type ConversationMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  markdown?: boolean;
};

const INITIAL_GREETING = "您好，我会结合您提供的资料整理五大处方。请先说说最想改善什么。";

function formatDocumentMessage(documents: ChatDocumentAttachment[]): string {
  return documents.length === 1 ? `已上传资料：${documents[0].fileName}` : `已上传 ${documents.length} 份资料`;
}

interface PrescriptionConversationProps {
  localSessionId: string;
  seniorMode: boolean;
  /** A completed report is persisted with the local conversation session. */
  hasExistingDraft: boolean;
  onPrescriptionDraftGenerated: (draft: FivePrescriptionDraft) => void;
}

/**
 * A bounded, chat-native collection flow.  Documents are parsed and registered
 * by the shared composer before their IDs are attached to the encrypted intake.
 * The server remains the authority for ownership, ten-document limits and the
 * complete 273k-character input check before generation.
 */
export function PrescriptionConversation({
  localSessionId,
  seniorMode,
  hasExistingDraft,
  onPrescriptionDraftGenerated,
}: PrescriptionConversationProps) {
  const [intake, setIntake] = useState<ClinicalIntake | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [generationFailed, setGenerationFailed] = useState(false);
  const [generationFailureMessageId, setGenerationFailureMessageId] = useState<string | null>(null);
  const [generationComplete, setGenerationComplete] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [manualAnswers, setManualAnswers] = useState<Record<string, string>>({});
  const [manualSaving, setManualSaving] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const generationStartedRef = useRef(false);
  const turnSubmissionInFlightRef = useRef(false);
  const generationAbortControllerRef = useRef<AbortController | null>(null);
  const manualFieldRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});

  useEffect(() => {
    let live = true;
    // The parent keys this component by session so every intake gets a fresh
    // state instance. Keep the ref explicit because it gates retries.
    generationStartedRef.current = false;
    void startClinicalIntake({ localSessionId, kind: "prescription" }).then(
      async (result) => {
        if (!live) return;
        setIntake(result);
        try {
          const history = await listPrescriptionDrafts(result.intake_id);
          if (!live) return;
          const latest = history.items[0];
          if (latest) {
            generationStartedRef.current = true;
            setGenerationComplete(true);
            onPrescriptionDraftGenerated(latest.draft);
            const latestReview = latest.reviews[0];
            const latestAmendment = latest.reviews.find((review) => review.amended_markdown);
            setMessages([
              {
                id: "restored",
                role: "assistant",
                text: "已恢复最近一次五大处方草案，您可以在右侧查看。",
              },
              ...(latestReview
                ? [
                    {
                      id: `review-${latestReview.review_id}`,
                      role: "assistant" as const,
                      text:
                        latestReview.decision === "approved"
                          ? `临床复核意见：已通过。${latestReview.review_note}`
                          : `临床复核意见：请补充后再复核。${latestReview.review_note}`,
                    },
                  ]
                : []),
              ...(latestAmendment?.amended_markdown
                ? [
                    {
                      id: `amendment-${latestAmendment.review_id}`,
                      role: "assistant" as const,
                      text: `## 医生修订内容\n\n${latestAmendment.amended_markdown}`,
                      markdown: true,
                    },
                  ]
                : []),
            ]);
          } else {
            setMessages([{ id: "welcome", role: "assistant", text: INITIAL_GREETING }]);
          }
        } catch (error) {
          if (!live) return;
          setMessages([{ id: "welcome", role: "assistant", text: INITIAL_GREETING }]);
          toast.show(error instanceof Error ? error.message : "草案记录暂未恢复");
        }
        setLoading(false);
      },
      (error: unknown) => {
        if (!live) return;
        setLoading(false);
        toast.show(error instanceof Error ? error.message : "五大处方暂时不可用，请稍后重试");
      },
    );
    return () => { live = false; };
  }, [localSessionId, onPrescriptionDraftGenerated]);

  useEffect(() => {
    if (!generating) return;
    const timer = window.setInterval(() => setElapsedSeconds((seconds) => seconds + 1), 1_000);
    return () => window.clearInterval(timer);
  }, [generating]);

  useEffect(() => () => {
    // Leaving the clinical view must use the same durable cancellation path as
    // the visible stop control; a navigation event is not a successful stop.
    generationAbortControllerRef.current?.abort();
  }, []);

  const append = (role: ConversationMessage["role"], text: string) => {
    const id = crypto.randomUUID();
    setMessages((current) => [...current, { id, role, text }]);
    return id;
  };

  const generate = async (readyIntake: ClinicalIntake) => {
    if (generationStartedRef.current) return;
    generationStartedRef.current = true;
    setGenerationFailed(false);
    if (generationFailureMessageId) {
      setMessages((current) => current.filter((message) => message.id !== generationFailureMessageId));
      setGenerationFailureMessageId(null);
    }
    setGenerationComplete(false);
    setGenerating(true);
    setStopping(false);
    setElapsedSeconds(0);
    const controller = new AbortController();
    generationAbortControllerRef.current = controller;
    try {
      const draft = await generatePrescriptionDraft(readyIntake.intake_id, { signal: controller.signal });
      append("assistant", "五大处方草案已生成，可以查看草案内容。 ");
      onPrescriptionDraftGenerated(draft);
      setGenerationComplete(true);
    } catch (error) {
      generationStartedRef.current = false;
      if (error instanceof GerclawApiError && error.code === "PRESCRIPTION_GENERATION_CANCELLED") {
        append("assistant", "已停止生成，未完成内容不会保存为草案。您可以补充信息后重新生成。 ");
      } else {
        setGenerationFailed(true);
        setGenerationFailureMessageId(
          append("assistant", error instanceof Error ? error.message : "暂时无法生成草案，请重试。 ")
        );
      }
    } finally {
      if (generationAbortControllerRef.current === controller) {
        generationAbortControllerRef.current = null;
      }
      setGenerating(false);
      setStopping(false);
    }
  };

  const stopGeneration = () => {
    if (!generating || stopping) return;
    setStopping(true);
    generationAbortControllerRef.current?.abort();
  };

  const handleManualCompletion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!intake || manualSaving) return;
    const missingFields = prescriptionMissingFields(intake.fields, intake.missing_required_fields);
    const prepared = prepareManualPrescriptionAnswers(missingFields, manualAnswers);
    if (prepared.firstMissingFieldId) {
      setManualError("请填写全部缺失信息后再保存。");
      manualFieldRefs.current[prepared.firstMissingFieldId]?.focus();
      return;
    }
    setManualSaving(true);
    setManualError(null);
    try {
      const next = await updateClinicalIntake({
        intakeId: intake.intake_id,
        expectedRevision: intake.revision,
        answers: prepared.answers,
      });
      setIntake(next);
      if (next.status === "information_complete_pending_governance") {
        setManualAnswers({});
        append("assistant", "关键信息已补齐，接下来生成待临床复核草案。 ");
        void generate(next);
      } else {
        setManualError("仍有必填信息未完成，请继续核对。");
      }
    } catch (error) {
      if (error instanceof GerclawApiError && error.status === 409) {
        try {
          setIntake(await getClinicalIntake(intake.intake_id));
          setManualError("信息已在其他页面更新，请核对后重新保存。");
        } catch {
          setManualError("暂时无法读取最新信息，请稍后重试。");
        }
      } else {
        setManualError("补充信息未保存，请重试。");
      }
    } finally {
      setManualSaving(false);
    }
  };

  const handleSend = async (
    text: string,
    images: ImageAttachment[] | undefined,
    documents: ChatDocumentAttachment[] = [],
  ) => {
    // A text Enter event and an immediate click can arrive before React has
    // painted the disabled send control. Keep a synchronous lock so both
    // paths cannot submit the same intake revision.
    if (
      !intake ||
      loading ||
      generating ||
      generationStartedRef.current ||
      turnSubmissionInFlightRef.current ||
      intake.conversation_turns >= PRESCRIPTION_COMPLETING_MAX_TURNS
    ) return false;
    turnSubmissionInFlightRef.current = true;
    setSending(true);
    const documentIds = [...new Set([
      ...intake.document_ids,
      ...documents.flatMap((document) => document.serverDocumentId ? [document.serverDocumentId] : []),
    ])];
    if (documentIds.length > 10) {
      toast.show("一次最多使用 10 份资料");
      turnSubmissionInFlightRef.current = false;
      setSending(false);
      return false;
    }
    try {
      const turn = await processPrescriptionConversationTurn({
        intakeId: intake.intake_id,
        expectedRevision: intake.revision,
        message: text.trim() || "请先阅读我上传的资料并判断还需要什么信息。",
        documentIds,
        images,
      });
      setIntake(turn.intake);
      if (text.trim()) append("user", text.trim());
      else if (documents.length) append("user", formatDocumentMessage(documents));
      else if (images?.length) append("user", `已上传 ${images.length} 张病例图片`);
      if (turn.ready_to_generate) {
        void generate(turn.intake);
      } else if (turn.intake.conversation_turns >= PRESCRIPTION_COMPLETING_MAX_TURNS) {
        append("assistant", "已完成 5 轮信息补充。为保证安全，请在下方核对缺失字段；信息完整前不会生成草案。 ");
      } else {
        append("assistant", turn.assistant_message);
      }
      return true;
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "信息暂未保存，请重试");
      return false;
    } finally {
      turnSubmissionInFlightRef.current = false;
      setSending(false);
    }
  };

  const retryGeneration = () => {
    if (intake?.status === "information_complete_pending_governance") void generate(intake);
  };

  const turnProgress = prescriptionTurnProgress(
    intake?.conversation_turns ?? 0,
    PRESCRIPTION_COMPLETING_MAX_TURNS,
  );
  const turnLimitReached = Boolean(
    intake?.status === "collecting" && turnProgress.limitReached,
  );
  const manualFields = intake
    ? prescriptionMissingFields(intake.fields, intake.missing_required_fields)
    : [];

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-background">
      <section className="min-h-0 flex-1 overflow-y-auto" aria-label="五大处方对话">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6 sm:px-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                "max-w-[88%] rounded-2xl px-4 py-3 leading-relaxed shadow-sm",
                message.role === "user"
                  ? "self-end bg-primary text-primary-foreground"
                  : "self-start border border-border bg-muted/50 text-foreground",
                seniorMode ? "text-lg" : "text-sm",
              )}
            >
              {message.markdown ? <MarkdownRenderer content={message.text} /> : message.text}
            </div>
          ))}
          {loading && <p className={cn("text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>正在准备对话…</p>}
          {intake?.status === "collecting" && (
            <p
              className={cn("text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}
              role="status"
              aria-live="polite"
            >
              信息补充：已完成 {turnProgress.completed}/{PRESCRIPTION_COMPLETING_MAX_TURNS} 轮，
              还可对话补充 {turnProgress.remaining} 轮。
            </p>
          )}
          {sending && !generating && (
            <div className={cn("flex items-center gap-2 self-start rounded-2xl border border-border bg-muted/50 px-4 py-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")} role="status" aria-live="polite">
              <span className="codex-activity-dots" aria-hidden="true">
                <span className="codex-activity-dot" />
                <span className="codex-activity-dot" />
                <span className="codex-activity-dot" />
              </span>
              正在整理资料…
            </div>
          )}
          {generating && (
            <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 self-start rounded-2xl border border-border bg-muted/50 px-4 py-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")} role="status" aria-live="polite">
              <span className="inline-flex items-center gap-2 font-medium text-foreground">
                <span className="codex-activity-dots" aria-hidden="true">
                  <span className="codex-activity-dot" />
                  <span className="codex-activity-dot" />
                  <span className="codex-activity-dot" />
                </span>
                {stopping ? "正在安全停止" : "正在整理资料并生成草案"}
              </span>
              <span className="tabular-nums">已执行 {String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:{String(elapsedSeconds % 60).padStart(2, "0")}</span>
              <Button type="button" variant="outline" size="sm" onClick={stopGeneration} disabled={stopping}>
                <Square className="size-3.5" aria-hidden="true" />
                {stopping ? "正在停止" : "停止生成"}
              </Button>
            </div>
          )}
          {!generating && !hasExistingDraft && !generationComplete && intake?.status === "information_complete_pending_governance" && (
            <Button variant={generationFailed ? "outline" : "default"} className="self-start" onClick={retryGeneration}>
              {generationFailed ? <RefreshCw className="size-4" /> : null}
              {generationFailed ? "重新生成" : "生成五大处方草案"}
            </Button>
          )}
          {turnLimitReached && (
            <section
              className="space-y-4 rounded-xl border border-amber-500/50 bg-amber-50/70 p-4 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100"
              aria-labelledby="prescription-manual-completion-title"
            >
              <div className={cn("space-y-1", seniorMode ? "text-lg" : "text-sm")}>
                <h2 id="prescription-manual-completion-title" className={cn("font-semibold", seniorMode && "text-xl")}>
                  请核对缺失信息
                </h2>
                <p>对话补充已达到 5 轮上限。信息完整前不会生成五大处方草案。</p>
              </div>
              <form className="space-y-4" onSubmit={handleManualCompletion}>
                {manualFields.map((field) => (
                  <div key={field.id} className="space-y-2">
                    <label htmlFor={`prescription-manual-${field.id}`} className={cn("block font-medium", seniorMode && "text-lg")}>
                      {field.label}（必填）
                    </label>
                    <textarea
                      ref={(element) => { manualFieldRefs.current[field.id] = element; }}
                      id={`prescription-manual-${field.id}`}
                      value={manualAnswers[field.id] ?? ""}
                      onChange={(event) => setManualAnswers((current) => ({
                        ...current,
                        [field.id]: event.target.value.slice(0, field.max_length),
                      }))}
                      maxLength={field.max_length}
                      className={cn(
                        "min-h-24 w-full rounded-md border border-input bg-background p-3 text-foreground",
                        seniorMode && "min-h-32 text-lg",
                      )}
                    />
                  </div>
                ))}
                {manualError && <p role="alert" className={cn("font-medium text-destructive", seniorMode ? "text-lg" : "text-sm")}>{manualError}</p>}
                <Button type="submit" disabled={manualSaving || manualFields.length === 0} className={cn(seniorMode && "min-h-12 px-5 text-lg")}>
                  {manualSaving ? "正在保存…" : "保存并继续生成"}
                </Button>
              </form>
            </section>
          )}
        </div>
      </section>
      {intake?.status !== "information_complete_pending_governance" && !turnLimitReached && (
        <ChatInput
          onSend={handleSend}
          isGenerating={generating}
          isSending={sending}
          prescriptionConversation
          placeholderOverride="输入文字、上传资料或使用语音…"
        />
      )}
    </div>
  );
}
