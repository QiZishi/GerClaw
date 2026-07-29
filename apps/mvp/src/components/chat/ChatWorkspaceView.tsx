"use client";

import { HeartHandshake } from "lucide-react";

import { ChatInput } from "@/components/chat/ChatInput";
import { ChatWorkspaceHeader } from "@/components/chat/ChatWorkspaceHeader";
import type {
  ChatDocumentAttachment,
  ChatSendAccepted,
} from "@/components/chat/composer/types";
import { MessageList } from "@/components/chat/MessageList";
import { WelcomePage } from "@/components/chat/WelcomePage";
import { CgaAssessment } from "@/components/cga/CgaAssessment";
import { ChronicCareLedger } from "@/components/chronic/ChronicCareLedger";
import { ClinicalIntakeForm } from "@/components/prescription/ClinicalIntakeForm";
import { PrescriptionConversation } from "@/components/prescription/PrescriptionConversation";
import { RiskAlertLedger } from "@/components/risk-alert/RiskAlertLedger";
import { SkillManager } from "@/components/skills/SkillManager";
import { cn } from "@/lib/utils";
import type { AnswerVersion } from "@/services/gerclaw/run-contract";
import type { FivePrescriptionDraft } from "@/services/gerclaw/schemas";
import type {
  ChatActionType,
  ImageAttachment,
  Message,
  Role,
} from "@/types";

interface ChatWorkspaceViewProps {
  mounted: boolean;
  mainView: "chat" | "skills";
  chatAction: ChatActionType;
  role: Role;
  seniorMode: boolean;
  sidebarCollapsed: boolean;
  currentSessionId: string | null;
  currentSessionTitle: string;
  hasExistingPrescriptionDraft: boolean;
  messages: Message[];
  isGenerating: boolean;
  contextLoading: boolean;
  onReturnToChat: () => void;
  onExampleClick: (text: string) => void;
  onStartAction: (action: ChatActionType) => void;
  onExitAction: () => void;
  onPrescriptionDraftGenerated: (draft: FivePrescriptionDraft) => void;
  onRegenerate: (messageId: string) => void;
  onShare: (messageId: string) => void;
  onDelete: (messageId: string) => void;
  onAnswerVersionSelected: (
    sessionId: string,
    messageId: string,
    version: AnswerVersion,
  ) => Promise<void>;
  onSend: (
    text: string,
    images?: ImageAttachment[],
    documents?: ChatDocumentAttachment[],
    requestedCapabilities?: string[],
  ) =>
    | boolean
    | void
    | ChatSendAccepted
    | Promise<boolean | void | ChatSendAccepted>;
  onStop: () => void;
}

export function ChatWorkspaceView({
  mounted,
  mainView,
  chatAction,
  role,
  seniorMode,
  sidebarCollapsed,
  currentSessionId,
  currentSessionTitle,
  hasExistingPrescriptionDraft,
  messages,
  isGenerating,
  contextLoading,
  onReturnToChat,
  onExampleClick,
  onStartAction,
  onExitAction,
  onPrescriptionDraftGenerated,
  onRegenerate,
  onShare,
  onDelete,
  onAnswerVersionSelected,
  onSend,
  onStop,
}: ChatWorkspaceViewProps) {
  const actionTitles: Partial<Record<ChatActionType, string>> = {
    prescription: role === "doctor" ? "五大处方草案" : "五大处方计划",
    companion: "暖心陪伴",
    cga: "老年综合评估",
    "drug-review": "用药审查",
    "chronic-care": "我的慢病记录",
    "risk-alerts": "我的安全提醒",
    "health-profile": "查看健康画像",
  };

  if (!mounted) {
    return (
      <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
        <WelcomePage
          onExampleClick={() => {}}
          onStartAction={() => {}}
          role="patient"
          seniorMode={false}
        />
      </main>
    );
  }

  if (mainView === "skills") {
    return (
      <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
        <ChatWorkspaceHeader
          mainView={mainView}
          chatAction={chatAction}
          seniorMode={seniorMode}
          sidebarCollapsed={sidebarCollapsed}
          currentSessionTitle={currentSessionTitle}
          showConversationHeader={false}
          onReturnToChat={onReturnToChat}
          onExitAction={onExitAction}
        />
        <div className="min-h-0 flex-1">
          <SkillManager />
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
      <ChatWorkspaceHeader
        mainView={mainView}
        chatAction={chatAction}
        seniorMode={seniorMode}
        sidebarCollapsed={sidebarCollapsed}
        currentSessionTitle={currentSessionTitle}
        showConversationHeader={
          chatAction !== "cga" &&
          (chatAction !== "none" ||
            Boolean(currentSessionId && messages.length > 0))
        }
        actionTitle={actionTitles[chatAction]}
        onReturnToChat={onReturnToChat}
        onExitAction={onExitAction}
      />

      {messages.length === 0 && chatAction === "none" ? (
        <WelcomePage
          onExampleClick={onExampleClick}
          onStartAction={onStartAction}
          role={role}
          seniorMode={seniorMode}
        />
      ) : chatAction === "cga" ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <CgaAssessment onExit={onExitAction} />
        </div>
      ) : chatAction === "prescription" ? (
        currentSessionId && (
          <PrescriptionConversation
            key={currentSessionId}
            localSessionId={currentSessionId}
            seniorMode={seniorMode}
            hasExistingDraft={hasExistingPrescriptionDraft}
            onPrescriptionDraftGenerated={onPrescriptionDraftGenerated}
          />
        )
      ) : chatAction === "drug-review" ? (
        currentSessionId && (
          <ClinicalIntakeForm
            localSessionId={currentSessionId}
            kind="medication_review"
            seniorMode={seniorMode}
            isClinician={role === "doctor" || role === "admin"}
            onExit={onExitAction}
          />
        )
      ) : chatAction === "chronic-care" ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ChronicCareLedger seniorMode={seniorMode} />
        </div>
      ) : chatAction === "risk-alerts" ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <RiskAlertLedger seniorMode={seniorMode} />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {chatAction === "companion" && (
            <section
              className={cn(
                "mx-auto mt-4 flex w-full max-w-3xl items-start gap-3 border-l-4 border-primary bg-primary/5 px-4 py-3 text-left",
                seniorMode ? "text-lg leading-8" : "text-sm leading-6",
              )}
              aria-label="暖心陪伴模式说明"
            >
              <HeartHandshake
                className="mt-1 size-5 shrink-0 text-primary"
                aria-hidden="true"
              />
              <div>
                <p className="font-semibold text-foreground">暖心陪伴</p>
                <p className="text-muted-foreground">
                  我是一位 AI，可以听您说说心里话。本次不读取健康档案、上传资料或技能，也不替代医疗咨询或紧急援助。
                </p>
              </div>
            </section>
          )}
          {messages.length > 0 && (
            <MessageList
              messages={messages}
              onRegenerate={onRegenerate}
              onShare={onShare}
              onDelete={onDelete}
              onAnswerVersionSelected={onAnswerVersionSelected}
            />
          )}
        </div>
      )}

      {(chatAction === "none" || chatAction === "companion") && (
        <ChatInput
          onSend={onSend}
          isGenerating={isGenerating}
          onStop={onStop}
          onStartAction={onStartAction}
          contextLoading={contextLoading}
          companionMode={chatAction === "companion"}
        />
      )}
    </main>
  );
}
