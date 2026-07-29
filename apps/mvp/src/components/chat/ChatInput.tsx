"use client";

import { useState, useRef, useEffect, useLayoutEffect } from "react";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { useSkillStore } from "@/stores/skillStore";
import { replaceSessionSkills } from "@/services/gerclaw/skills";
import { INPUT_LIMITS, MEDICAL_DISCLAIMER, ALLOWED_IMAGE_MIME_TYPES } from "@/lib/constants";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { recognizeAudio } from "@/services/voice/asr";
import { parseFile } from "@/services/document/mineru";
import { registerParsedDocument, revokeParsedDocument } from "@/services/gerclaw/documents";
import { generateId } from "@/lib/format";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import type { FileTag as UploadFileTag, ImageAttachment } from "@/types";
import {
  ComposerAttachmentTray,
  type PendingComposerImage as PendingImage,
} from "@/components/chat/composer/ComposerAttachmentTray";
import {
  ComposerToolbar,
  type ComposerAction,
} from "@/components/chat/composer/ComposerToolbar";
import { ComposerRecordingPanel } from "@/components/chat/composer/ComposerRecordingPanel";
import { ComposerSubmitControl } from "@/components/chat/composer/ComposerSubmitControl";

export interface ChatDocumentAttachment {
  localId: string;
  fileName: string;
  mediaType: string;
  source: "mineru" | "local-text";
  markdown: string;
  serverDocumentId?: string;
  documentSessionId?: string;
}

interface ChatSendAccepted {
  accepted: true;
  documentBindings?: Record<string, string>;
  documentSessionId?: string;
}

interface ChatInputProps {
  onSend?: (
    text: string,
    images?: ImageAttachment[],
    documents?: ChatDocumentAttachment[]
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

const ALLOWED_FILE_EXT = [".pdf", ".docx", ".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp"];
const ALLOWED_FILE_MIME = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/markdown",
  "text/plain",
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
];

function documentMediaType(file: File): string | null {
  if (ALLOWED_FILE_MIME.includes(file.type)) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "pdf") return "application/pdf";
  if (extension === "docx") {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  if (extension === "md") return "text/markdown";
  if (extension === "txt") return "text/plain";
  return null;
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
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [pendingDocuments, setPendingDocuments] = useState<UploadFileTag[]>([]);
  const [uploadedDocCount, setUploadedDocCount] = useState(0);
  const rawDocumentsRef = useRef<Map<string, File>>(new Map());
  const documentScopeRef = useRef<string | undefined>(currentSessionId);
  const previousSessionIdRef = useRef<string | undefined>(currentSessionId);
  const [showLimitDialog, setShowLimitDialog] = useState(false);
  const [limitDialogMessage, setLimitDialogMessage] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const transcriptionAbortRef = useRef<AbortController | null>(null);
  const documentParseAbortRef = useRef<Map<string, AbortController>>(new Map());

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

  const {
    isRecording,
    recordingDuration,
    audioLevel,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useAudioRecorder();

  const micDisabled = !isOnline || !asrAvailable || isTranscribing || isGenerating || isSending;

  useLayoutEffect(() => {
    const previousSessionId = previousSessionIdRef.current;
    documentScopeRef.current = currentSessionId;
    previousSessionIdRef.current = currentSessionId;
    if (!previousSessionId || previousSessionId === currentSessionId) return;

    const hadDraft = Boolean(text.trim()) || pendingImages.length > 0 || pendingDocuments.length > 0 || isTranscribing || isRecording;
    rawDocumentsRef.current.clear();
    documentParseAbortRef.current.forEach((controller) => controller.abort());
    documentParseAbortRef.current.clear();
    setPendingDocuments([]);
    setUploadedDocCount(0);
    setPendingImages((previous) => {
      previous.forEach((image) => URL.revokeObjectURL(image.previewUrl));
      return [];
    });
    setText("");
    transcriptionAbortRef.current?.abort();
    transcriptionAbortRef.current = null;
    setIsTranscribing(false);
    cancelRecording();
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (textareaRef.current) {
      textareaRef.current.style.height = "52px";
    }
    if (hadDraft) {
      toast.show("已切换会话，未发送的文字、图片和文档已清空；原会话资料不会自动带入新对话");
    }
  }, [cancelRecording, currentSessionId, isRecording, isTranscribing, pendingDocuments.length, pendingImages.length, text]);

  useEffect(() => {
    const pendingParses = documentParseAbortRef.current;
    return () => {
      pendingImages.forEach((img) => URL.revokeObjectURL(img.previewUrl));
      transcriptionAbortRef.current?.abort();
      pendingParses.forEach((controller) => controller.abort());
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "52px";
    }
  }, []);

  const readFileAsBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.split(",")[1] ?? "";
        resolve(base64);
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  };

  const handleImageSelect = () => {
    imageInputRef.current?.click();
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const parsePendingDocument = async (fileData: UploadFileTag, file: File) => {
    documentParseAbortRef.current.get(fileData.id)?.abort();
    const controller = new AbortController();
    documentParseAbortRef.current.set(fileData.id, controller);
    const scopeAtStart = documentScopeRef.current;
    setPendingDocuments((previous) =>
      previous.map((item) =>
        item.id === fileData.id ? { ...item, status: "parsing" } : item
      )
    );
    try {
      const result = await parseFile(file, controller.signal);
      if (controller.signal.aborted || documentParseAbortRef.current.get(fileData.id) !== controller) {
        return;
      }
      const mediaType = documentMediaType(file);
      if (!mediaType) throw new Error("文件类型无法安全识别");
      let serverDocumentId: string | undefined;
      if (currentSessionId) {
        const registered = await registerParsedDocument({
          localSessionId: currentSessionId,
          filename: file.name,
          mediaType,
          source: result.source,
          markdown: result.markdown,
        });
        serverDocumentId = registered.document_id;
      }
      if (controller.signal.aborted || documentParseAbortRef.current.get(fileData.id) !== controller) {
        if (serverDocumentId && scopeAtStart) {
          await revokeParsedDocument(scopeAtStart, serverDocumentId);
        }
        return;
      }
      if (documentScopeRef.current !== scopeAtStart) {
        if (serverDocumentId && scopeAtStart) {
          await revokeParsedDocument(scopeAtStart, serverDocumentId);
        }
        setPendingDocuments((previous) =>
          previous.map((item) =>
            item.id === fileData.id
              ? {
                  ...item,
                  status: "failed",
                  progress: 0,
                  errorMessage: "会话已切换，请重新上传或点击重试后再使用此文档",
                }
              : item
          )
        );
        return;
      }
      const completed: UploadFileTag = {
        ...fileData,
        status: "done",
        progress: 100,
        parsedMarkdown: result.markdown,
        parsedAt: Date.now(),
        serverDocumentId,
        documentSessionId: serverDocumentId ? currentSessionId ?? undefined : undefined,
      };
      setPendingDocuments((previous) =>
        previous.map((item) => (item.id === fileData.id ? completed : item))
      );
      setUploadedDocCount((count) => count + 1);
      // 卡片状态与输入框上方的固定说明已经完整说明下一步；不再用长 toast
      // 遮挡移动端内容或重复打断用户。
    } catch (error) {
      if (controller.signal.aborted || documentParseAbortRef.current.get(fileData.id) !== controller) {
        return;
      }
      const errorMessage = error instanceof Error ? error.message : "文档解析失败，请稍后重试";
      setPendingDocuments((previous) =>
        previous.map((item) =>
          item.id === fileData.id
            ? { ...item, status: "failed", progress: 0, errorMessage }
            : item
        )
      );
      toast.show(`解析 ${file.name} 失败：${errorMessage}`);
    } finally {
      if (documentParseAbortRef.current.get(fileData.id) === controller) {
        documentParseAbortRef.current.delete(fileData.id);
      }
    }
  };

  const cancelPendingDocument = (id: string) => {
    const controller = documentParseAbortRef.current.get(id);
    if (!controller) return;
    controller.abort();
    documentParseAbortRef.current.delete(id);
    setPendingDocuments((previous) =>
      previous.map((item) =>
        item.id === id
          ? {
              ...item,
              status: "failed",
              progress: 0,
              errorMessage: "已取消解析；如仍需要该文档，请点击重试",
            }
          : item
      )
    );
    toast.show("已取消文档解析，原文件仍保留，可随时重试。");
  };

  const retryPendingDocument = (id: string) => {
    const fileData = pendingDocuments.find((item) => item.id === id);
    const rawFile = rawDocumentsRef.current.get(id);
    if (!fileData || !rawFile) {
      toast.show("原文件已不可用，请重新选择文件");
      return;
    }
    setPendingDocuments((previous) =>
      previous.map((item) =>
        item.id === id
          ? { ...item, status: "parsing", errorMessage: undefined }
          : item
      )
    );
    void parsePendingDocument(fileData, rawFile);
  };

  const removePendingDocument = async (id: string) => {
    documentParseAbortRef.current.get(id)?.abort();
    documentParseAbortRef.current.delete(id);
    const existing = pendingDocuments.find((item) => item.id === id);
    if (existing?.serverDocumentId && existing.documentSessionId) {
      try {
        await revokeParsedDocument(existing.documentSessionId, existing.serverDocumentId);
      } catch (error) {
        toast.show(error instanceof Error ? error.message : "文档撤销失败，请重试");
        return;
      }
    }
    setPendingDocuments((previous) => previous.filter((item) => item.id !== id));
    rawDocumentsRef.current.delete(id);
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const isImage = (file: File) => ALLOWED_IMAGE_MIME_TYPES.includes(file.type as (typeof ALLOWED_IMAGE_MIME_TYPES)[number]);
    const documentFiles: File[] = [];
    const imageFiles: File[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (isImage(file)) {
        imageFiles.push(file);
      } else {
        documentFiles.push(file);
      }
    }

    if (uploadedDocCount + pendingDocuments.length + documentFiles.length > INPUT_LIMITS.maxFileCount) {
      setLimitDialogMessage(`已达到最大文件上传数量（${INPUT_LIMITS.maxFileCount}个），请先删除部分文件后再上传。`);
      setShowLimitDialog(true);
      e.target.value = "";
      return;
    }

    if (imageFiles.length > 0) {
      const remaining = INPUT_LIMITS.maxImageCount - pendingImages.length;
      const toProcess = imageFiles.slice(0, remaining);
      const newImages: PendingImage[] = [];
      for (const file of toProcess) {
        if (file.size > INPUT_LIMITS.maxImageSize) {
          toast.show(`图片 ${file.name} 超过 5MB 限制`);
          continue;
        }
        try {
          const base64 = await readFileAsBase64(file);
          const previewUrl = URL.createObjectURL(file);
          newImages.push({
            id: generateId("img"),
            mimeType: file.type,
            base64,
            previewUrl,
            alt: file.name,
          });
        } catch {
          toast.show(`读取图片 ${file.name} 失败`);
        }
      }
      if (newImages.length > 0) {
        setPendingImages((prev) => [...prev, ...newImages]);
      }
    }

    if (documentFiles.length > 0) {
      for (const file of documentFiles) {
        const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
        const typeOk = ALLOWED_FILE_MIME.includes(file.type) || ALLOWED_FILE_EXT.includes(ext);
        if (!typeOk) {
          toast.show(`不支持的文件类型：${file.name}，请上传 PDF/DOCX/MD/图片`);
          continue;
        }
        if (file.size > INPUT_LIMITS.maxFileSize) {
          toast.show(`文件 ${file.name} 超过 10MB 限制`);
          continue;
        }
        const id = generateId("file");
        const fileData: UploadFileTag = {
          id,
          fileName: file.name,
          fileType: ext.slice(1),
          fileSize: file.size,
          status: "parsing",
        };
        rawDocumentsRef.current.set(id, file);
        setPendingDocuments((previous) => [...previous, fileData]);
        void parsePendingDocument(fileData, file);
      }
    }

    e.target.value = "";
  };

  const handleImageChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const remaining = INPUT_LIMITS.maxImageCount - pendingImages.length;
    if (remaining <= 0) {
      setLimitDialogMessage(`已达到最大图片上传数量（${INPUT_LIMITS.maxImageCount}张），请先删除部分图片后再上传。`);
      setShowLimitDialog(true);
      e.target.value = "";
      return;
    }

    const newImages: PendingImage[] = [];
    for (let i = 0; i < Math.min(files.length, remaining); i++) {
      const file = files[i];
      if (!ALLOWED_IMAGE_MIME_TYPES.includes(file.type as (typeof ALLOWED_IMAGE_MIME_TYPES)[number])) {
        toast.show(`不支持的图片格式：${file.type}，请上传 JPG/PNG/WebP/GIF`);
        continue;
      }
      if (file.size > INPUT_LIMITS.maxImageSize) {
        toast.show(`图片 ${file.name} 超过 5MB 限制`);
        continue;
      }
      try {
        const base64 = await readFileAsBase64(file);
        const previewUrl = URL.createObjectURL(file);
        newImages.push({
          id: generateId("img"),
          mimeType: file.type,
          base64,
          previewUrl,
          alt: file.name,
        });
      } catch {
        toast.show(`读取图片 ${file.name} 失败`);
      }
    }

    if (newImages.length > 0) {
      setPendingImages((prev) => [...prev, ...newImages]);
    }
    e.target.value = "";
  };

  const removePendingImage = (id: string) => {
    setPendingImages((prev) => {
      const img = prev.find((p) => p.id === id);
      if (img) URL.revokeObjectURL(img.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
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
  const hasUnboundParsedDocuments = pendingDocuments.some(
    (document) =>
      document.status === "done" &&
      Boolean(document.parsedMarkdown) &&
      !document.serverDocumentId,
  );

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
    const images: ImageAttachment[] | undefined = pendingImages.length > 0
      ? pendingImages.map((p) => ({ mimeType: p.mimeType, base64: p.base64, alt: p.alt }))
      : undefined;
    const documents: ChatDocumentAttachment[] = pendingDocuments
      .filter((item) => item.status === "done" && item.parsedMarkdown)
      .map((item) => {
        const rawFile = rawDocumentsRef.current.get(item.id);
        return {
          localId: item.id,
          fileName: item.fileName,
          mediaType: rawFile ? documentMediaType(rawFile) ?? "" : "",
          source: item.fileType === "md" || item.fileType === "txt" ? "local-text" : "mineru",
          markdown: item.parsedMarkdown ?? "",
          serverDocumentId: item.serverDocumentId,
          documentSessionId: item.documentSessionId,
        };
      });
    const result = await onSend?.(trimmed, images, documents);
    if (result === false || !result) return;
    if (typeof result === "object" && result.documentBindings && result.documentSessionId) {
      setPendingDocuments((previous) =>
        previous.map((item) => {
          const serverDocumentId = result.documentBindings?.[item.id];
          return serverDocumentId
            ? { ...item, serverDocumentId, documentSessionId: result.documentSessionId }
            : item;
        })
      );
    }
    setText("");
    setPendingImages((prev) => {
      prev.forEach((img) => URL.revokeObjectURL(img.previewUrl));
      return [];
    });
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = "52px";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !isRecording && !isTranscribing) {
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

  const formatDuration = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const handleMicStart = async () => {
    if (isTranscribing || isGenerating) return;
    try {
      await startRecording();
    } catch (err) {
      const message = err instanceof Error ? err.message : "无法启动录音";
      toast.show(message);
    }
  };

  const handleRecordingCancel = () => {
    try {
      cancelRecording();
    } catch {
      toast.show("取消录音失败");
    }
  };

  const handleTranscriptionCancel = () => {
    const controller = transcriptionAbortRef.current;
    if (!controller) return;
    controller.abort();
    transcriptionAbortRef.current = null;
    setIsTranscribing(false);
    toast.show("已取消语音识别，您可以继续编辑或重新录音。");
  };

  const handleRecordingFinish = async () => {
    try {
      const blob = await stopRecording();
      const controller = new AbortController();
      transcriptionAbortRef.current = controller;
      setIsTranscribing(true);
      try {
        const recognizedText = await recognizeAudio(blob, controller.signal);
        if (!controller.signal.aborted && recognizedText) {
          setText((prev) => {
            const newText = prev ? prev + " " + recognizedText : recognizedText;
            return newText.slice(0, INPUT_LIMITS.maxMessageLength);
          });
          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.style.height = "auto";
              textareaRef.current.style.height = `${Math.max(52, Math.min(textareaRef.current.scrollHeight, 200))}px`;
              textareaRef.current.focus();
            }
          }, 50);
        }
      } catch {
        if (!controller.signal.aborted) {
          toast.show("语音识别失败，请重试");
        }
      } finally {
        if (transcriptionAbortRef.current === controller) {
          transcriptionAbortRef.current = null;
          setIsTranscribing(false);
        }
      }
    } catch {
      toast.show("录音失败，请重试");
    }
  };

  if (isRecording) {
    return (
      <ComposerRecordingPanel
        audioLevel={audioLevel}
        duration={formatDuration(recordingDuration)}
        seniorMode={seniorMode}
        onCancel={handleRecordingCancel}
        onFinish={() => void handleRecordingFinish()}
      />
    );
  }

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="max-w-3xl mx-auto">
        {!companionMode && (
          <ComposerAttachmentTray
            documents={pendingDocuments}
            images={pendingImages}
            loadedSkillIds={loadedSkillIds}
            availableSkills={availableSkills}
            seniorMode={seniorMode}
            onCancelDocument={cancelPendingDocument}
            onRetryDocument={retryPendingDocument}
            onRemoveDocument={(id) => void removePendingDocument(id)}
            onRemoveImage={removePendingImage}
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
              onChange={handleImageChange}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept={ALLOWED_FILE_EXT.join(",")}
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
          </>
        )}

        <div className="rounded-xl border border-border bg-muted/50 transition-[border-color,box-shadow,background-color] duration-[var(--motion-popover)] ease-[var(--motion-ease-out)] focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring/40">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
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
                onMicStart={() => void handleMicStart()}
                onCancelTranscription={handleTranscriptionCancel}
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

      <Dialog open={showLimitDialog} onOpenChange={setShowLimitDialog}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>提示</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {limitDialogMessage}
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="outline">我知道了</Button>} />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
