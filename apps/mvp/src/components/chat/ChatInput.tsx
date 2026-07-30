"use client";

import { useState, useRef, useEffect, useLayoutEffect } from "react";
import { useAppStore } from "@/stores/appStore";
import { useSkillStore } from "@/stores/skillStore";
import { replaceSessionSkills } from "@/services/gerclaw/skills";
import { INPUT_LIMITS } from "@/lib/constants";
import { toast } from "@/components/ui/toast";
import type { ImageAttachment } from "@/types";
import type { ComposerAction } from "@/components/chat/composer/ComposerToolbar";
import { ComposerInputPanel } from "@/components/chat/composer/ComposerInputPanel";
import { ComposerRecordingPanel } from "@/components/chat/composer/ComposerRecordingPanel";
import { useComposerAttachments } from "@/components/chat/composer/useComposerAttachments";
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
  onQueue?: (instruction: string) => Promise<boolean>;
  onSteer?: (instruction: string) => Promise<boolean>;
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
  onQueue,
  onSteer,
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
  const [directiveSubmitting, setDirectiveSubmitting] = useState<
    "queue" | "steer" | null
  >(null);
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

  const placeholder = placeholderOverride ?? (isGenerating
    ? "输入新要求，可选择立即调整或排队继续…"
    : !mounted
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

  const handleRunDirective = async (mode: "queue" | "steer") => {
    const instruction = text.trim();
    if (!instruction || directiveSubmitting || !isGenerating || !isOnline) return;
    setDirectiveSubmitting(mode);
    try {
      const accepted =
        mode === "queue"
          ? await onQueue?.(instruction)
          : await onSteer?.(instruction);
      if (!accepted) return;
      setText("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "52px";
      }
    } finally {
      setDirectiveSubmitting(null);
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
    <ComposerInputPanel
      text={text}
      placeholder={placeholder}
      role={role}
      seniorMode={seniorMode}
      mounted={mounted}
      isGuest={isGuest}
      isOnline={isOnline}
      asrAvailable={asrAvailable}
      isGenerating={Boolean(isGenerating)}
      isSending={isSending}
      directiveSubmitting={directiveSubmitting}
      isTranscribing={isTranscribing}
      contextLoading={contextLoading}
      companionMode={companionMode}
      prescriptionConversation={prescriptionConversation}
      micDisabled={micDisabled}
      dragActive={dragActive}
      hasUnboundParsedDocuments={hasUnboundParsedDocuments}
      pendingImages={pendingImages}
      pendingDocuments={pendingDocuments}
      loadedSkillIds={loadedSkillIds}
      availableSkills={availableSkills}
      selectedCapabilityIds={selectedCapabilityIds}
      limitDialogMessage={limitDialogMessage}
      bindTextarea={(element) => {
        textareaRef.current = element;
      }}
      bindImageInput={(element) => {
        imageInputRef.current = element;
      }}
      bindFileInput={(element) => {
        fileInputRef.current = element;
      }}
      onPickImage={() => imageInputRef.current?.click()}
      onPickFile={() => fileInputRef.current?.click()}
      onInput={handleInput}
      onKeyDown={handleKeyDown}
      onPasteFiles={(files) => void addFiles(files)}
      onAddImages={(files) => void addImages(files)}
      onAddFiles={(files) => void addFiles(files)}
      onDragActiveChange={setDragActive}
      onCancelDocument={cancelDocument}
      onRetryDocument={retryDocument}
      onRemoveDocument={(id) => void removeDocument(id)}
      onRemoveImage={removeImage}
      onRemoveSkill={(id) => void handleRemoveLoadedSkill(id)}
      onCapabilityChange={setSelectedCapabilityIds}
      onAction={handleStartAction}
      onSend={() => void handleSend()}
      onStop={onStop}
      onQueue={() => void handleRunDirective("queue")}
      onSteer={() => void handleRunDirective("steer")}
      onMicStart={() => void startVoice()}
      onCancelTranscription={cancelTranscription}
      onLimitDialogChange={setLimitDialogMessage}
    />
  );
}
