"use client";

import { useState, useRef, useEffect, useLayoutEffect } from "react";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { useSkillStore } from "@/stores/skillStore";
import { replaceSessionSkills } from "@/services/gerclaw/skills";
import { INPUT_LIMITS, MEDICAL_DISCLAIMER, ALLOWED_IMAGE_MIME_TYPES } from "@/lib/constants";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import type { ImageAttachment } from "@/types";
import { ComposerAttachmentTray } from "@/components/chat/composer/ComposerAttachmentTray";
import {
  ComposerToolbar,
  type ComposerAction,
} from "@/components/chat/composer/ComposerToolbar";
import { ComposerRecordingPanel } from "@/components/chat/composer/ComposerRecordingPanel";
import { ComposerSubmitControl } from "@/components/chat/composer/ComposerSubmitControl";
import {
  COMPOSER_FILE_ACCEPT,
  useComposerAttachments,
} from "@/components/chat/composer/useComposerAttachments";
import { shouldSubmitComposerKey } from "@/components/chat/composer/composer-contract";
import {
  formatRecordingDuration,
  useComposerVoice,
} from "@/components/chat/composer/useComposerVoice";
import type {
  ChatDocumentAttachment,
  ChatSendAccepted,
} from "@/components/chat/composer/types";

export type { ChatDocumentAttachment } from "@/components/chat/composer/types";

interface ChatInputProps {
  onSend?: (
    text: string,
    images?: ImageAttachment[],
    documents?: ChatDocumentAttachment[],
    requestedCapabilities?: string[],
  ) => boolean | void | ChatSendAccepted | Promise<boolean | void | ChatSendAccepted>;
  isGenerating?: boolean;
  /** A request is being accepted by the backend; block duplicate sends without pretending generation has started. */
  isSending?: boolean;
  onStop?: () => void;
  onStartAction?: (action: "prescription" | "cga" | "drug-review" | "health-profile") => void;
  contextLoading?: boolean;
  /** The companion backend rejects files and Skills; keep the controls truthful. */
  companionMode?: boolean;
  /** Five-prescription collection keeps the familiar chat composer focused on voice, text and files. */
  prescriptionConversation?: boolean;
  placeholderOverride?: string;
}

export function ChatInput({
  onSend,
  isGenerating,
  isSending = false,
  onStop,
  onStartAction,
  contextLoading = false,
  companionMode = false,
  prescriptionConversation = false,
  placeholderOverride,
}: ChatInputProps) {
  const [mounted, setMounted] = useState(false);
  const role = useAppStore((s) => s.role);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const isGuest = useAppStore((s) => s.isGuest);
  const loadedSkillIds = useAppStore((s) => s.loadedSkillIds);
  const setLoadedSkills = useAppStore((s) => s.setLoadedSkills);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const availableSkills = useSkillStore((s) => s.skills);
  const skillStatus = useSkillStore((s) => s.status);
  const refreshSkills = useSkillStore((s) => s.refresh);
  const isOnline = useAppStore((s) => s.isOnline);
  const asrAvailable = useAppStore((s) => s.asrAvailable);

  const handleStartAction = (action: ComposerAction) => {
    if (onStartAction) {
      onStartAction(action);
      return;
    }
    toast.show("当前页面暂时无法启动该流程。请返回对话页面后重试，或使用文字描述您的情况。");
  };

  const [text, setText] = useState("");
  const [selectedCapabilityIds, setSelectedCapabilityIds] = useState<string[]>([]);
  const previousSessionIdRef = useRef<string | undefined>(currentSessionId);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    pendingImages,
    pendingDocuments,
    hasAttachments,
    hasUnboundParsedDocuments,
    limitDialogMessage,
    dragActive,
    imageInputRef,
    fileInputRef,
    setLimitDialogMessage,
    setDragActive,
    addFiles,
    addImages,
    resetAttachments,
    clearSentImages,
    cancelDocument,
    retryDocument,
    removeDocument,
    removeImage,
    buildImages,
    buildDocuments,
    applyDocumentBindings,
  } = useComposerAttachments(currentSessionId);
  const {
    isRecording,
    recordingDuration,
    audioLevel,
    isTranscribing,
    micDisabled,
    resetVoice,
    startVoice,
    cancelVoice,
    finishVoice,
    cancelTranscription,
  } = useComposerVoice({
    textAreaRef: textareaRef,
    setText,
    isOnline,
    asrAvailable,
    isGenerating: Boolean(isGenerating),
    isSending,
  });

  const handleRemoveLoadedSkill = async (id: string) => {
    const next = loadedSkillIds.filter((skillId) => skillId !== id);
    try {
      setLoadedSkills(currentSessionId ? await replaceSessionSkills(currentSessionId, next) : next);
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "技能选择未保存");
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  useEffect(() => {
    if (loadedSkillIds.length > 0 && skillStatus === "idle") {
      void refreshSkills();
    }
  }, [loadedSkillIds.length, refreshSkills, skillStatus]);

  useLayoutEffect(() => {
    const previousSessionId = previousSessionIdRef.current;
    previousSessionIdRef.current = currentSessionId;
    if (!previousSessionId || previousSessionId === currentSessionId) return;

    const hadDraft = Boolean(text.trim()) || hasAttachments || isTranscribing || isRecording;
    resetAttachments();
    setSelectedCapabilityIds([]);
    setText("");
    resetVoice();
    if (textareaRef.current) {
      textareaRef.current.style.height = "52px";
    }
    if (hadDraft) {
      toast.show("已切换会话，未发送的文字、图片和文档已清空；原会话资料不会自动带入新对话");
    }
  }, [
    currentSessionId,
    hasAttachments,
    isRecording,
    isTranscribing,
    resetAttachments,
    resetVoice,
    text,
  ]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "52px";
    }
  }, []);

  const handleImageSelect = () => {
    imageInputRef.current?.click();
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const placeholder = placeholderOverride ?? (!mounted
    ? "描述您的健康问题…"
    : contextLoading
      ? "正在恢复当前会话的技能，请稍候…"
    : companionMode
      ? "想说些什么？我会认真听您说…"
    : role === "doctor"
      ? seniorMode
        ? "请描述患者病情或评估需求…"
        : "请输入患者病情或评估需求…"
      : seniorMode
        ? "请描述您想咨询的健康问题…"
        : "描述您的健康问题…");
  const handleSend = async () => {
    const trimmed = text.trim();
    if (companionMode && (pendingImages.length > 0 || pendingDocuments.length > 0)) {
      toast.show("陪伴模式仅支持文字或语音交流，请先移除资料后再发送。");
      return;
    }
    if (
      (!trimmed && (pendingImages.length === 0 || hasUnboundParsedDocuments)) ||
      isGenerating ||
      isSending ||
      isTranscribing ||
      contextLoading ||
      !isOnline
    ) return;
    const images = buildImages();
    const documents = buildDocuments();
    const result = await onSend?.(trimmed, images, documents, selectedCapabilityIds);
    if (result === false || !result) return;
    if (typeof result === "object") applyDocumentBindings(result);
    setText("");
    setSelectedCapabilityIds([]);
    clearSentImages();
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = "52px";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (shouldSubmitComposerKey({
      key: e.key,
      shiftKey: e.shiftKey,
      isComposing: e.nativeEvent.isComposing,
      keyCode: e.keyCode,
      isRecording,
      isTranscribing,
    })) {
      e.preventDefault();
      void handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value.slice(0, INPUT_LIMITS.maxMessageLength));
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.max(52, Math.min(ta.scrollHeight, 200))}px`;
  };

  if (isRecording) {
    return (
      <ComposerRecordingPanel
        audioLevel={audioLevel}
        duration={formatRecordingDuration(recordingDuration)}
        seniorMode={seniorMode}
        onCancel={cancelVoice}
        onFinish={() => void finishVoice()}
      />
    );
  }

  return (
    <div
      className={cn(
        "relative border-t border-border bg-background px-4 py-3",
        dragActive && !companionMode && "bg-primary/5",
      )}
      onDragEnter={(event) => {
        if (companionMode || !event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        setDragActive(true);
      }}
      onDragOver={(event) => {
        if (companionMode || !event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setDragActive(false);
      }}
      onDrop={(event) => {
        if (companionMode) return;
        event.preventDefault();
        setDragActive(false);
        void addFiles(Array.from(event.dataTransfer.files));
      }}
    >
      {dragActive && !companionMode && (
        <div
          className="pointer-events-none absolute inset-2 z-20 grid place-items-center rounded-xl border-2 border-dashed border-primary bg-background/95 text-base font-medium text-primary"
          role="status"
        >
          松开即可添加到本次对话
        </div>
      )}
      <div className="max-w-3xl mx-auto">
        {!companionMode && (
          <ComposerAttachmentTray
            documents={pendingDocuments}
            images={pendingImages}
            loadedSkillIds={loadedSkillIds}
            availableSkills={availableSkills}
            seniorMode={seniorMode}
            onCancelDocument={cancelDocument}
            onRetryDocument={retryDocument}
            onRemoveDocument={(id) => void removeDocument(id)}
            onRemoveImage={removeImage}
            onRemoveSkill={(id) => void handleRemoveLoadedSkill(id)}
          />
        )}
        {!companionMode && hasUnboundParsedDocuments && (
          <p className={cn("mb-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-muted-foreground", seniorMode ? "text-lg leading-8" : "text-sm")} role="status">
            资料已解析，发送即可。
          </p>
        )}

        {!companionMode && (
          <>
            <input
              ref={imageInputRef}
              type="file"
              accept={ALLOWED_IMAGE_MIME_TYPES.join(",")}
              multiple
              className="hidden"
              onChange={(event) => {
                void addImages(Array.from(event.currentTarget.files ?? []));
                event.currentTarget.value = "";
              }}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept={COMPOSER_FILE_ACCEPT}
              multiple
              className="hidden"
              onChange={(event) => {
                void addFiles(Array.from(event.currentTarget.files ?? []));
                event.currentTarget.value = "";
              }}
            />
          </>
        )}

        <div className="rounded-xl border border-border bg-muted/50 transition-[border-color,box-shadow,background-color] duration-[var(--motion-popover)] ease-[var(--motion-ease-out)] focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring/40">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            onPaste={(event) => {
              if (companionMode) return;
              const files = Array.from(event.clipboardData.files);
              if (files.length === 0) return;
              event.preventDefault();
              void addFiles(files);
            }}
            placeholder={isTranscribing ? (seniorMode ? "正在识别语音…" : "识别中…") : hasUnboundParsedDocuments ? (seniorMode ? "请说出您想了解的问题…" : "请输入您想了解的问题…") : placeholder}
            rows={1}
            disabled={isTranscribing || contextLoading || isSending}
            className={cn(
              "w-full resize-none bg-transparent border-0 outline-none px-4 py-3 text-base leading-relaxed placeholder:text-muted-foreground max-h-[200px] overflow-y-auto disabled:opacity-60 transition-colors",
              seniorMode && "text-lg"
            )}
            style={{ minHeight: "52px" }}
          />

          <div className="flex items-end justify-between gap-2 px-2 py-1.5 border-t border-border/60">
            {companionMode ? (
              <p className={cn("px-2 text-muted-foreground", seniorMode ? "text-base" : "text-xs")}>
                仅使用当前对话，不读取健康档案、资料或技能
              </p>
            ) : (
              <ComposerToolbar
                disabled={isTranscribing || contextLoading || isSending}
                role={role}
                mounted={mounted}
                seniorMode={seniorMode}
                onAction={handleStartAction}
                onPickImage={handleImageSelect}
                onPickFile={handleFileSelect}
                prescriptionConversation={prescriptionConversation}
                isGuest={isGuest}
                selectedCapabilityIds={selectedCapabilityIds}
                onCapabilityChange={setSelectedCapabilityIds}
              />
            )}

            <div className="flex items-center gap-1">
              <ComposerSubmitControl
                isGenerating={Boolean(isGenerating)}
                isTranscribing={isTranscribing}
                isSending={isSending}
                canSend={Boolean(text.trim()) || (pendingImages.length > 0 && !hasUnboundParsedDocuments)}
                isOnline={isOnline}
                asrAvailable={asrAvailable}
                micDisabled={micDisabled}
                seniorMode={seniorMode}
                onSend={() => void handleSend()}
                onStop={onStop}
                onMicStart={() => void startVoice()}
                onCancelTranscription={cancelTranscription}
              />
            </div>
          </div>
        </div>

        <div className={cn(
          "mt-1.5 text-muted-foreground",
          seniorMode ? "text-lg" : "text-[11px]"
        )}>
          {contextLoading && (
            <span
              role="status"
              className={cn("mb-1 block text-primary", seniorMode && "text-lg")}
            >
              正在恢复当前会话的技能，恢复完成后即可发送。
            </span>
          )}
          {companionMode
            ? "此模式提供情感支持，不替代医疗咨询、心理治疗或紧急援助。"
            : MEDICAL_DISCLAIMER}
        </div>
      </div>

      <Dialog
        open={limitDialogMessage !== null}
        onOpenChange={(open) => {
          if (!open) setLimitDialogMessage(null);
        }}
      >
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>提示</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {limitDialogMessage ?? ""}
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="outline">我知道了</Button>} />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
