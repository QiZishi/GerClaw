"use client";

import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
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
  const [generating, setGenerating] = useState(false);
  const [generationFailed, setGenerationFailed] = useState(false);
  const [generationFailureMessageId, setGenerationFailureMessageId] = useState<string | null>(null);
  const [generationComplete, setGenerationComplete] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const generationStartedRef = useRef(false);

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
            setMessages([
              {
                id: "restored",
                role: "assistant",
                text: "已恢复最近一次五大处方草案，您可以在右侧查看。",
              },
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
    setElapsedSeconds(0);
    try {
      const draft = await generatePrescriptionDraft(readyIntake.intake_id);
      append("assistant", "五大处方草案已生成。您可以在右侧查看。 ");
      onPrescriptionDraftGenerated(draft);
      setGenerationComplete(true);
    } catch (error) {
      generationStartedRef.current = false;
      setGenerationFailed(true);
      setGenerationFailureMessageId(
        append("assistant", error instanceof Error ? error.message : "暂时无法生成草案，请重试。 ")
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleSend = async (
    text: string,
    images: ImageAttachment[] | undefined,
    documents: ChatDocumentAttachment[] = [],
  ) => {
    if (!intake || loading || generating) return false;
    const documentIds = [...new Set([
      ...intake.document_ids,
      ...documents.flatMap((document) => document.serverDocumentId ? [document.serverDocumentId] : []),
    ])];
    if (documentIds.length > 10) {
      toast.show("一次最多使用 10 份资料");
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
          {generating && (
            <div className={cn("self-start rounded-2xl border border-border bg-muted/50 px-4 py-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")} role="status">
              正在整理资料并生成草案 · 已执行 {String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:{String(elapsedSeconds % 60).padStart(2, "0")}
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
          prescriptionConversation
          placeholderOverride="输入文字、上传资料或使用语音…"
        />
      )}
    </div>
  );
}
