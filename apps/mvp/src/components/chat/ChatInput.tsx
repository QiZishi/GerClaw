"use client";

import { useState, useRef, useEffect, useLayoutEffect } from "react";
import Image from "next/image";
import {
  Check,
  ClipboardCheck,
  FileSearch,
  ImageIcon,
  Mic,
  Paperclip,
  Pill,
  SendHorizonal,
  Square,
  UserRound,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAppStore } from "@/stores/appStore";
import { useSkillStore } from "@/stores/skillStore";
import { SkillTag } from "@/components/skills/SkillTag";
import { SkillSelector } from "@/components/skills/SkillSelector";
import { FileTag } from "@/components/document/FileTag";
import { DocumentToolCard } from "@/components/document/DocumentToolCard";
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

interface PendingImage {
  id: string;
  mimeType: string;
  base64: string;
  previewUrl: string;
  alt?: string;
}

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
  onStop?: () => void;
  onStartAction?: (action: "prescription" | "cga" | "drug-review" | "health-profile") => void;
  contextLoading?: boolean;
  /** The companion backend rejects files and Skills; keep the controls truthful. */
  companionMode?: boolean;
}

function WaveformBars({ audioLevel }: { audioLevel: number }) {
  const barCount = 28;
  return (
    <div className="flex items-center justify-center gap-[3px] flex-1 px-4 overflow-hidden">
      {Array.from({ length: barCount }).map((_, i) => {
        const centerDist = Math.abs(i - barCount / 2) / (barCount / 2);
        const baseHeight = 4 + (1 - centerDist) * 8;
        const levelMultiplier = 0.4 + audioLevel * 1.8;
        const height = Math.min(baseHeight * levelMultiplier, 28);
        const isActive = audioLevel > 0.05;
        return (
          <div
            key={i}
            className={cn(
              "w-[3px] rounded-full transition-all duration-100",
              isActive ? "bg-gray-800 dark:bg-gray-200" : "bg-gray-300 dark:bg-gray-600"
            )}
            style={{
              height: `${height}px`,
            }}
          />
        );
      })}
    </div>
  );
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

function FunctionButtonGroup({
  disabled,
  role,
  mounted,
  seniorMode,
  onSetChatAction,
  onPickImage,
  onPickFile,
}: {
  disabled: boolean;
  role: "patient" | "doctor" | "visitor";
  mounted: boolean;
  seniorMode: boolean;
  onSetChatAction: (action: "prescription" | "cga" | "drug-review" | "health-profile") => void;
  onPickImage: () => void;
  onPickFile: () => void;
}) {
  const isDoctor = mounted && role === "doctor";
  return (
    <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto overscroll-x-contain pb-1">
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size={seniorMode ? "default" : "icon"}
              className={cn("btn-icon shrink-0", seniorMode && "order-1 h-12 gap-2 px-3 text-base")}
              onClick={onPickImage}
              aria-label="上传图片"
              disabled={disabled}
            />
          }
        >
          <ImageIcon className="size-4" />
          {seniorMode && <span>图片</span>}
        </TooltipTrigger>
        <TooltipContent>上传图片</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size={seniorMode ? "default" : "icon"}
              className={cn("btn-icon shrink-0", seniorMode && "order-2 h-12 gap-2 px-3 text-base")}
              onClick={onPickFile}
              aria-label="上传文件或图片"
              disabled={disabled}
            />
          }
        >
          <Paperclip className="size-4" />
          {seniorMode && <span>文件</span>}
        </TooltipTrigger>
        <TooltipContent>上传文件（PDF/DOCX/MD/图片）</TooltipContent>
      </Tooltip>
      <SkillSelector showLabel={seniorMode}>
        <Button
          variant="ghost"
          size={seniorMode ? "default" : "icon"}
          className={cn("btn-icon shrink-0", seniorMode && "order-3 h-12 min-w-24 px-4 text-lg")}
          aria-label="选择当前对话的临床技能"
          disabled={disabled}
        />
      </SkillSelector>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size={seniorMode ? "default" : "icon"}
              className={cn("btn-icon shrink-0", seniorMode && "order-4 h-12 gap-2 px-3 text-base")}
              onClick={() => onSetChatAction("prescription")}
              aria-label="五大处方信息收集"
              disabled={disabled}
            />
          }
        >
          <Pill className="size-4" />
          {seniorMode && <span>处方信息</span>}
        </TooltipTrigger>
        <TooltipContent>五大处方信息收集</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size={seniorMode ? "default" : "icon"}
              className={cn("btn-icon shrink-0", seniorMode && "order-5 h-12 gap-2 px-3 text-base")}
              onClick={() => onSetChatAction("cga")}
              aria-label="老年综合评估"
              disabled={disabled}
            />
          }
        >
          <ClipboardCheck className="size-4" />
          {seniorMode && <span>评估</span>}
        </TooltipTrigger>
        <TooltipContent>老年综合评估</TooltipContent>
      </Tooltip>
      {isDoctor && (
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size={seniorMode ? "default" : "icon"}
                className={cn("btn-icon shrink-0", seniorMode && "order-6 h-12 gap-2 px-3 text-base")}
                onClick={() => onSetChatAction("drug-review")}
                aria-label="用药信息收集"
                disabled={disabled}
              />
            }
          >
            <FileSearch className="size-4" />
            {seniorMode && <span>用药信息</span>}
          </TooltipTrigger>
          <TooltipContent>用药信息收集</TooltipContent>
        </Tooltip>
      )}
      {(isDoctor || (mounted && role === "patient")) && (
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size={seniorMode ? "default" : "icon"}
                className={cn("btn-icon shrink-0", seniorMode && "order-7 h-12 gap-2 px-3 text-base")}
                onClick={() => onSetChatAction("health-profile")}
                aria-label="查看我的健康记录"
                disabled={disabled}
              />
            }
          >
            <UserRound className="size-4" />
            {seniorMode && <span>档案</span>}
          </TooltipTrigger>
          <TooltipContent>查看我的健康记录</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

export function ChatInput({
  onSend,
  isGenerating,
  onStop,
  onStartAction,
  contextLoading = false,
  companionMode = false,
}: ChatInputProps) {
  const [mounted, setMounted] = useState(false);
  const role = useAppStore((s) => s.role);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const loadedSkillIds = useAppStore((s) => s.loadedSkillIds);
  const setLoadedSkills = useAppStore((s) => s.setLoadedSkills);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const availableSkills = useSkillStore((s) => s.skills);
  const skillStatus = useSkillStore((s) => s.status);
  const refreshSkills = useSkillStore((s) => s.refresh);
  const isOnline = useAppStore((s) => s.isOnline);
  const asrAvailable = useAppStore((s) => s.asrAvailable);

  const handleStartAction = (action: "prescription" | "cga" | "drug-review" | "health-profile") => {
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

  const micDisabled = !isOnline || !asrAvailable || isTranscribing || isGenerating;

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

  const placeholder = !mounted
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
        : "描述您的健康问题…";
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
      <div className="border-t border-border bg-background px-4 py-3">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-3 rounded-xl bg-muted/70 px-3 py-3">
            <button
              type="button"
              onClick={handleRecordingCancel}
              className={cn(
                "flex items-center justify-center shrink-0 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors",
                seniorMode ? "size-14" : "size-11"
              )}
              aria-label="取消录音"
            >
              <X className={cn(seniorMode ? "size-6" : "size-5")} />
            </button>

            <WaveformBars audioLevel={audioLevel} />

            <span className={cn(
              "shrink-0 tabular-nums font-medium text-gray-700 dark:text-gray-300 min-w-[48px] text-center",
              seniorMode ? "text-xl" : "text-lg"
            )}>
              {formatDuration(recordingDuration)}
            </span>

            <button
              type="button"
              onClick={handleRecordingFinish}
              className={cn(
                "flex items-center justify-center shrink-0 rounded-full transition-colors",
                seniorMode ? "size-14" : "size-11",
                "bg-indigo-600 hover:bg-indigo-700 text-white"
              )}
              aria-label="完成录音"
            >
              <Check className={cn(seniorMode ? "size-6" : "size-5")} strokeWidth={3} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="max-w-3xl mx-auto">
        {(!companionMode && (loadedSkillIds.length > 0 || pendingImages.length > 0 || pendingDocuments.length > 0)) && (
          <div className="flex flex-wrap gap-2 mb-2">
            {pendingDocuments.map((file) => (
              <div key={file.id} className="min-w-0 space-y-2">
                {file.status === "done" ? (
                  <DocumentToolCard
                    data={file}
                    onRemove={(id) => removePendingDocument(id)}
                  />
                ) : (
                  <FileTag
                    data={file}
                    onRetry={file.status === "failed" ? retryPendingDocument : undefined}
                    onCancel={file.status === "parsing" ? cancelPendingDocument : undefined}
                    onRemove={file.status === "failed" ? (id) => void removePendingDocument(id) : undefined}
                  />
                )}
              </div>
            ))}
            {pendingImages.map((img) => (
              <div key={img.id} className="relative group">
                <Image
                  src={img.previewUrl}
                  alt={img.alt ?? "上传图片"}
                  width={64}
                  height={64}
                  unoptimized
                  className="w-16 h-16 object-cover rounded-md border border-border"
                />
                <button
                  type="button"
                  onClick={() => removePendingImage(img.id)}
                  className={cn(
                    "absolute -top-1.5 -right-1.5 size-5 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow",
                    seniorMode && "static mt-1 min-h-12 w-full gap-1 rounded-md px-2 text-base opacity-100"
                  )}
                  aria-label="移除图片"
                >
                  <X className="size-3" />
                  {seniorMode && <span>移除图片</span>}
                </button>
              </div>
            ))}
            {loadedSkillIds.map((id) => (
              <SkillTag
                key={id}
                skill={
                  availableSkills.find((skill) => skill.skill_id === id) ?? {
                    skill_id: id,
                    name: "正在读取技能",
                    source: "builtin",
                  }
                }
                removable
                onRemove={(skillId) => void handleRemoveLoadedSkill(skillId)}
                className={cn(seniorMode && "min-h-12 px-3 text-lg")}
              />
            ))}
          </div>
        )}
        {!companionMode && hasUnboundParsedDocuments && (
          <p className={cn("mb-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-muted-foreground", seniorMode ? "text-lg leading-8" : "text-sm")} role="status">
            文档已准备好。请在下方提出您想了解的问题，发送后才会安全加入本次对话。
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

        <div className="rounded-xl border border-border bg-muted/50 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring/40 transition-all duration-200">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
          placeholder={isTranscribing ? (seniorMode ? "正在识别语音…" : "识别中…") : hasUnboundParsedDocuments ? (seniorMode ? "请说出您想了解的问题…" : "请输入您想了解的问题…") : placeholder}
            rows={1}
            disabled={isTranscribing || contextLoading}
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
              <FunctionButtonGroup
                disabled={isTranscribing || contextLoading}
                role={role}
                mounted={mounted}
                seniorMode={seniorMode}
                onSetChatAction={handleStartAction}
                onPickImage={handleImageSelect}
                onPickFile={handleFileSelect}
              />
            )}

            <div className="flex items-center gap-1">
              {isGenerating ? (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="destructive"
                        size={seniorMode ? "default" : "icon"}
                        className={cn("btn-icon", seniorMode && "h-12 gap-2 px-3 text-base")}
                        onClick={onStop}
                        aria-label="停止生成"
                      />
                    }
                  >
                  <Square className="size-4 fill-current" />
                  {seniorMode && <span>停止</span>}
                  </TooltipTrigger>
                  <TooltipContent>停止生成</TooltipContent>
                </Tooltip>
              ) : isTranscribing ? (
                <div className="flex items-center gap-2 px-1" role="status" aria-live="polite">
                  <span className={cn("whitespace-nowrap text-primary", seniorMode ? "text-lg" : "text-sm")}>
                    正在识别语音
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size={seniorMode ? "default" : "sm"}
                    className={cn("shrink-0", seniorMode && "min-h-12 px-3 text-base")}
                    onClick={handleTranscriptionCancel}
                  >
                    取消识别
                  </Button>
                </div>
              ) : text.trim() || (pendingImages.length > 0 && !hasUnboundParsedDocuments) ? (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="default"
                        size={seniorMode ? "default" : "icon"}
                        className={cn("btn-icon", seniorMode && "h-12 gap-2 px-3 text-base")}
                        onClick={() => void handleSend()}
                        aria-label="发送"
                        disabled={!isOnline || contextLoading}
                      />
                    }
                  >
                  <SendHorizonal className="size-4" />
                  {seniorMode && <span>发送</span>}
                  </TooltipTrigger>
                  <TooltipContent>
                    {!isOnline ? "网络已断开，请检查网络连接" : "发送"}
                  </TooltipContent>
                </Tooltip>
              ) : (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size={seniorMode ? "default" : "icon"}
                        className={cn("btn-icon", seniorMode && "h-12 gap-2 px-3 text-base")}
                        onClick={handleMicStart}
                        aria-label={micDisabled ? "语音服务暂时不可用" : "语音输入"}
                        disabled={micDisabled}
                      />
                    }
                  >
                  <Mic className={cn(seniorMode ? "size-5" : "size-4")} />
                  {seniorMode && <span>说话</span>}
                  </TooltipTrigger>
                  <TooltipContent>
                    {!isOnline 
                      ? "网络已断开，语音服务暂不可用" 
                      : !asrAvailable 
                        ? "语音服务暂时不可用" 
                        : "语音输入"}
                  </TooltipContent>
                </Tooltip>
              )}
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
