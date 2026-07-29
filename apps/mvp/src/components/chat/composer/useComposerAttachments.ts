"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { PendingComposerImage } from "@/components/chat/composer/ComposerAttachmentTray";
import type {
  ChatDocumentAttachment,
  ChatSendAccepted,
} from "@/components/chat/composer/types";
import { documentMediaType } from "@/components/chat/composer/document-media";
import { toast } from "@/components/ui/toast";
import { parseFile } from "@/services/document/mineru";
import {
  registerParsedDocument,
  revokeParsedDocument,
} from "@/services/gerclaw/documents";
import {
  ALLOWED_IMAGE_MIME_TYPES,
  INPUT_LIMITS,
} from "@/lib/constants";
import { generateId } from "@/lib/format";
import type { FileTag as UploadFileTag, ImageAttachment } from "@/types";

export const COMPOSER_FILE_ACCEPT = [
  ".pdf",
  ".docx",
  ".md",
  ".txt",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
].join(",");

const ALLOWED_FILE_EXTENSIONS = new Set(COMPOSER_FILE_ACCEPT.split(","));
const ALLOWED_FILE_MEDIA_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/markdown",
  "text/plain",
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
]);

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] ?? "");
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function useComposerAttachments(currentSessionId: string | null) {
  const [pendingImages, setPendingImages] = useState<PendingComposerImage[]>([]);
  const [pendingDocuments, setPendingDocuments] = useState<UploadFileTag[]>([]);
  const [uploadedDocumentCount, setUploadedDocumentCount] = useState(0);
  const [limitDialogMessage, setLimitDialogMessage] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingImagesRef = useRef<PendingComposerImage[]>([]);
  const rawDocumentsRef = useRef<Map<string, File>>(new Map());
  const parseControllersRef = useRef<Map<string, AbortController>>(new Map());
  const documentScopeRef = useRef<string | null>(currentSessionId);

  useLayoutEffect(() => {
    documentScopeRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    pendingImagesRef.current = pendingImages;
  }, [pendingImages]);

  useEffect(() => {
    const controllers = parseControllersRef.current;
    const rawDocuments = rawDocumentsRef.current;
    return () => {
      controllers.forEach((controller) => controller.abort());
      rawDocuments.clear();
      pendingImagesRef.current.forEach((image) => URL.revokeObjectURL(image.previewUrl));
    };
  }, []);

  const parseDocument = useCallback(async (fileData: UploadFileTag, file: File) => {
    parseControllersRef.current.get(fileData.id)?.abort();
    const controller = new AbortController();
    parseControllersRef.current.set(fileData.id, controller);
    const scopeAtStart = documentScopeRef.current;
    setPendingDocuments((current) =>
      current.map((item) => item.id === fileData.id ? { ...item, status: "parsing" } : item),
    );
    try {
      const result = await parseFile(file, controller.signal);
      if (controller.signal.aborted || parseControllersRef.current.get(fileData.id) !== controller) return;
      const mediaType = documentMediaType(file);
      if (!mediaType) throw new Error("文件类型无法安全识别");
      let serverDocumentId: string | undefined;
      if (scopeAtStart) {
        const registered = await registerParsedDocument({
          localSessionId: scopeAtStart,
          filename: file.name,
          mediaType,
          source: result.source,
          markdown: result.markdown,
        });
        serverDocumentId = registered.document_id;
      }
      if (controller.signal.aborted || parseControllersRef.current.get(fileData.id) !== controller) {
        if (serverDocumentId && scopeAtStart) {
          await revokeParsedDocument(scopeAtStart, serverDocumentId);
        }
        return;
      }
      if (documentScopeRef.current !== scopeAtStart) {
        if (serverDocumentId && scopeAtStart) {
          await revokeParsedDocument(scopeAtStart, serverDocumentId);
        }
        setPendingDocuments((current) =>
          current.map((item) =>
            item.id === fileData.id
              ? {
                  ...item,
                  status: "failed",
                  progress: 0,
                  errorMessage: "会话已切换，请重新上传或点击重试后再使用此文档",
                }
              : item,
          ),
        );
        return;
      }
      setPendingDocuments((current) =>
        current.map((item) =>
          item.id === fileData.id
            ? {
                ...fileData,
                status: "done",
                progress: 100,
                parsedMarkdown: result.markdown,
                parsedAt: Date.now(),
                serverDocumentId,
                documentSessionId: serverDocumentId ? scopeAtStart ?? undefined : undefined,
              }
            : item,
        ),
      );
      setUploadedDocumentCount((count) => count + 1);
    } catch (error) {
      if (controller.signal.aborted || parseControllersRef.current.get(fileData.id) !== controller) return;
      const errorMessage = error instanceof Error ? error.message : "文档解析失败，请稍后重试";
      setPendingDocuments((current) =>
        current.map((item) =>
          item.id === fileData.id
            ? { ...item, status: "failed", progress: 0, errorMessage }
            : item,
        ),
      );
      toast.show(`解析 ${file.name} 失败：${errorMessage}`);
    } finally {
      if (parseControllersRef.current.get(fileData.id) === controller) {
        parseControllersRef.current.delete(fileData.id);
      }
    }
  }, []);

  const addImages = useCallback(async (files: File[]) => {
    const remaining = INPUT_LIMITS.maxImageCount - pendingImages.length;
    if (remaining <= 0) {
      setLimitDialogMessage(`已达到最大图片上传数量（${INPUT_LIMITS.maxImageCount}张），请先删除部分图片后再上传。`);
      return;
    }
    const accepted: PendingComposerImage[] = [];
    for (const file of files.slice(0, remaining)) {
      if (!ALLOWED_IMAGE_MIME_TYPES.includes(file.type as (typeof ALLOWED_IMAGE_MIME_TYPES)[number])) {
        toast.show(`不支持的图片格式：${file.type || file.name}，请上传 JPG/PNG/WebP/GIF`);
        continue;
      }
      if (file.size > INPUT_LIMITS.maxImageSize) {
        toast.show(`图片 ${file.name} 超过 5MB 限制`);
        continue;
      }
      try {
        accepted.push({
          id: generateId("img"),
          mimeType: file.type,
          base64: await readFileAsBase64(file),
          previewUrl: URL.createObjectURL(file),
          alt: file.name,
        });
      } catch {
        toast.show(`读取图片 ${file.name} 失败`);
      }
    }
    if (accepted.length > 0) setPendingImages((current) => [...current, ...accepted]);
  }, [pendingImages.length]);

  const addFiles = useCallback(async (files: File[]) => {
    const imageFiles = files.filter((file) =>
      ALLOWED_IMAGE_MIME_TYPES.includes(file.type as (typeof ALLOWED_IMAGE_MIME_TYPES)[number]),
    );
    const documentFiles = files.filter((file) => !imageFiles.includes(file));
    if (
      uploadedDocumentCount + pendingDocuments.length + documentFiles.length
      > INPUT_LIMITS.maxFileCount
    ) {
      setLimitDialogMessage(`已达到最大文件上传数量（${INPUT_LIMITS.maxFileCount}个），请先删除部分文件后再上传。`);
      return;
    }
    if (imageFiles.length > 0) await addImages(imageFiles);
    for (const file of documentFiles) {
      const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
      if (!ALLOWED_FILE_MEDIA_TYPES.has(file.type) && !ALLOWED_FILE_EXTENSIONS.has(extension)) {
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
        fileType: extension.slice(1),
        fileSize: file.size,
        status: "parsing",
      };
      rawDocumentsRef.current.set(id, file);
      setPendingDocuments((current) => [...current, fileData]);
      void parseDocument(fileData, file);
    }
  }, [addImages, parseDocument, pendingDocuments.length, uploadedDocumentCount]);

  const resetAttachments = useCallback(() => {
    parseControllersRef.current.forEach((controller) => controller.abort());
    parseControllersRef.current.clear();
    rawDocumentsRef.current.clear();
    setPendingDocuments([]);
    setUploadedDocumentCount(0);
    setPendingImages((current) => {
      current.forEach((image) => URL.revokeObjectURL(image.previewUrl));
      return [];
    });
    if (imageInputRef.current) imageInputRef.current.value = "";
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const clearSentImages = useCallback(() => {
    setPendingImages((current) => {
      current.forEach((image) => URL.revokeObjectURL(image.previewUrl));
      return [];
    });
  }, []);

  const cancelDocument = useCallback((id: string) => {
    const controller = parseControllersRef.current.get(id);
    if (!controller) return;
    controller.abort();
    parseControllersRef.current.delete(id);
    setPendingDocuments((current) =>
      current.map((item) =>
        item.id === id
          ? {
              ...item,
              status: "failed",
              progress: 0,
              errorMessage: "已取消解析；如仍需要该文档，请点击重试",
            }
          : item,
      ),
    );
    toast.show("已取消文档解析，原文件仍保留，可随时重试。");
  }, []);

  const retryDocument = useCallback((id: string) => {
    const fileData = pendingDocuments.find((item) => item.id === id);
    const rawFile = rawDocumentsRef.current.get(id);
    if (!fileData || !rawFile) {
      toast.show("原文件已不可用，请重新选择文件");
      return;
    }
    void parseDocument({ ...fileData, status: "parsing", errorMessage: undefined }, rawFile);
  }, [parseDocument, pendingDocuments]);

  const removeDocument = useCallback(async (id: string) => {
    parseControllersRef.current.get(id)?.abort();
    parseControllersRef.current.delete(id);
    const existing = pendingDocuments.find((item) => item.id === id);
    if (existing?.serverDocumentId && existing.documentSessionId) {
      try {
        await revokeParsedDocument(existing.documentSessionId, existing.serverDocumentId);
      } catch (error) {
        toast.show(error instanceof Error ? error.message : "文档撤销失败，请重试");
        return;
      }
    }
    setPendingDocuments((current) => current.filter((item) => item.id !== id));
    rawDocumentsRef.current.delete(id);
  }, [pendingDocuments]);

  const removeImage = useCallback((id: string) => {
    setPendingImages((current) => {
      const image = current.find((item) => item.id === id);
      if (image) URL.revokeObjectURL(image.previewUrl);
      return current.filter((item) => item.id !== id);
    });
  }, []);

  const buildImages = (): ImageAttachment[] | undefined =>
    pendingImages.length === 0
      ? undefined
      : pendingImages.map((image) => ({
          mimeType: image.mimeType,
          base64: image.base64,
          alt: image.alt,
        }));

  const buildDocuments = (): ChatDocumentAttachment[] =>
    pendingDocuments
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

  const applyDocumentBindings = (result: ChatSendAccepted) => {
    if (!result.documentBindings || !result.documentSessionId) return;
    setPendingDocuments((current) =>
      current.map((item) => {
        const serverDocumentId = result.documentBindings?.[item.id];
        return serverDocumentId
          ? { ...item, serverDocumentId, documentSessionId: result.documentSessionId }
          : item;
      }),
    );
  };

  const hasUnboundParsedDocuments = pendingDocuments.some(
    (document) =>
      document.status === "done"
      && Boolean(document.parsedMarkdown)
      && !document.serverDocumentId,
  );

  return {
    pendingImages,
    pendingDocuments,
    hasAttachments: pendingImages.length > 0 || pendingDocuments.length > 0,
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
  };
}
