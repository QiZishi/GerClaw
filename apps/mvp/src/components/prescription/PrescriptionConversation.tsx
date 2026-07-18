"use client";

import { useEffect, useRef, useState } from "react";
import { RefreshCw, Square } from "lucide-react";
import { ChatInput, type ChatDocumentAttachment } from "@/components/chat/ChatInput";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { PRESCRIPTION_COMPLETING_MAX_TURNS } from "@/lib/constants";
import {
  generatePrescriptionDraft,
  listPrescriptionDrafts,
  processPrescriptionConversationTurn,
  startClinicalIntake,
} from "@/services/gerclaw/clinical-intakes";
import type { ClinicalIntake, FivePrescriptionDraft } from "@/services/gerclaw/schemas";
import type { ImageAttachment } from "@/types";
import { GerclawApiError } from "@/services/gerclaw/client";

type ConversationMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
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
  const generationStartedRef = useRef(false);
  const turnSubmissionInFlightRef = useRef(false);
  const generationAbortControllerRef = useRef<AbortController | null>(null);

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

  const handleSend = async (
    text: string,
    images: ImageAttachment[] | undefined,
    documents: ChatDocumentAttachment[] = [],
  ) => {
    // A text Enter event and an immediate click can arrive before React has
    // painted the disabled send control. Keep a synchronous lock so both
    // paths cannot submit the same intake revision.
    if (!intake || loading || generating || generationStartedRef.current || turnSubmissionInFlightRef.current) return false;
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
        append("assistant", "还需要补充关键信息后才能生成草案。请重新开始后继续补充。 ");
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
              {message.text}
            </div>
          ))}
          {loading && <p className={cn("text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>正在准备对话…</p>}
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
        </div>
      </section>
      {intake?.status !== "information_complete_pending_governance" && (
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
