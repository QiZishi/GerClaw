"use client";

import { useCallback, useRef, useState } from "react";
import { FileUp, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAppStore } from "@/stores/appStore";
import { INPUT_LIMITS } from "@/lib/constants";
import { formatFileSize, generateId } from "@/lib/format";
import { cn } from "@/lib/utils";
import { FileTag } from "./FileTag";
import type { FileTag as FileTagData, FileStatus } from "@/types";

interface FileUploadProps {
  className?: string;
  /** 文件解析完成回调（用于外层面板切换到预览） */
  onFileParsed?: (file: FileTagData) => void;
}

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/markdown",
  "text/plain",
  "image/png",
  "image/jpeg",
];

const ACCEPTED_EXT = [".pdf", ".docx", ".md", ".txt", ".png", ".jpg", ".jpeg"];

/**
 * §4.2.3 文件上传组件
 * 拖拽/点击上传，mock 模拟上传→解析→完成三阶段
 * 仅修改 appStore.uploadedFileIds（不调用真实接口）
 */
export function FileUpload({ className, onFileParsed }: FileUploadProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const uploadedFileIds = useAppStore((s) => s.uploadedFileIds);
  const addUploadedFile = useAppStore((s) => s.addUploadedFile);
  const removeUploadedFile = useAppStore((s) => s.removeUploadedFile);

  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FileTagData[]>([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showError = (msg: string) => {
    setError(msg);
    setTimeout(() => setError(null), 3000);
  };

  const simulateParse = useCallback(
    (file: FileTagData) => {
      // 上传阶段：500ms
      setFiles((prev) =>
        prev.map((f) =>
          f.id === file.id
            ? { ...f, status: "uploading" as FileStatus, progress: 30 }
            : f
        )
      );
      setTimeout(() => {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === file.id
              ? { ...f, status: "parsing" as FileStatus, progress: 70 }
              : f
          )
        );
        // 解析阶段：800ms
        setTimeout(() => {
          const mockContent = generateMockParsedMarkdown(file.fileName);
          setFiles((prev) =>
            prev.map((f) =>
              f.id === file.id
                ? {
                    ...f,
                    status: "done" as FileStatus,
                    progress: 100,
                    parsedMarkdown: mockContent,
                  }
                : f
            )
          );
          onFileParsed?.({
            ...file,
            status: "done",
            progress: 100,
            parsedMarkdown: mockContent,
          });
        }, 800);
      }, 500);
    },
    [onFileParsed]
  );

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;
      const current = files.length;
      const remaining = INPUT_LIMITS.maxFileCount - current;
      if (remaining <= 0) {
        showError(`最多上传 ${INPUT_LIMITS.maxFileCount} 个文件`);
        return;
      }
      Array.from(fileList).slice(0, remaining).forEach((raw) => {
        // 类型校验
        const ext = `.${raw.name.split(".").pop()?.toLowerCase()}`;
        const typeOk =
          ACCEPTED_TYPES.includes(raw.type) || ACCEPTED_EXT.includes(ext);
        if (!typeOk) {
          showError(`不支持的文件类型：${raw.name}`);
          return;
        }
        // 大小校验
        if (raw.size > INPUT_LIMITS.maxFileSize) {
          showError(
            `文件过大：${raw.name}（${formatFileSize(raw.size)}），上限 ${formatFileSize(
              INPUT_LIMITS.maxFileSize
            )}`
          );
          return;
        }
        const id = generateId("file");
        const newFile: FileTagData = {
          id,
          fileName: raw.name,
          fileType: ext.slice(1),
          fileSize: raw.size,
          status: "uploading",
          progress: 0,
        };
        setFiles((prev) => [...prev, newFile]);
        addUploadedFile(id);
        simulateParse(newFile);
      });
    },
    [files.length, addUploadedFile, simulateParse]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const handleRemove = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
    removeUploadedFile(id);
  };

  const handleRetry = (id: string) => {
    const file = files.find((f) => f.id === id);
    if (!file) return;
    setFiles((prev) =>
      prev.map((f) =>
        f.id === id ? { ...f, status: "uploading", progress: 0, errorMessage: undefined } : f
      )
    );
    simulateParse(file);
  };

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* 拖拽区 */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={cn(
          "m-3 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 cursor-pointer transition-colors",
          dragging
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/40 hover:bg-muted/50",
          seniorMode && "p-8"
        )}
        aria-label="点击或拖拽上传文件"
      >
        <div
          className={cn(
            "flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary",
            seniorMode && "size-12"
          )}
        >
          <Upload className={cn("size-5", seniorMode && "size-6")} />
        </div>
        <div className="text-center">
          <div
            className={cn(
              "text-sm font-medium",
              seniorMode && "text-base"
            )}
          >
            点击或拖拽文件到此处
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            支持 PDF / DOCX / MD / TXT / PNG / JPG
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            单文件 ≤ {formatFileSize(INPUT_LIMITS.maxFileSize)}，最多 {INPUT_LIMITS.maxFileCount} 个
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXT.join(",")}
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
          aria-hidden
        />
      </div>

      {/* 错误提示 */}
      {error && (
        <div
          role="alert"
          className="mx-3 mb-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
        >
          {error}
        </div>
      )}

      {/* 文件列表 */}
      {files.length > 0 && (
        <div className="px-3 pb-1 flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            已上传 {files.length} / {INPUT_LIMITS.maxFileCount}
          </span>
          <Button
            variant="ghost"
            size="xs"
            className="gap-1 text-xs"
            onClick={() => {
              files.forEach((f) => removeUploadedFile(f.id));
              setFiles([]);
            }}
          >
            <X className="size-3" />
            清空
          </Button>
        </div>
      )}
      <ScrollArea className="flex-1 min-h-0">
        <div className="px-3 pb-3 space-y-2">
          {files.map((f) => (
            <FileTag
              key={f.id}
              data={f}
              onRemove={handleRemove}
              onRetry={handleRetry}
            />
          ))}
          {files.length === 0 && (
            <div className="flex flex-col items-center gap-1 py-6 text-xs text-muted-foreground">
              <FileUp className="size-6 opacity-40" />
              <span>尚未上传文件</span>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* 已加载到输入框提示 */}
      {uploadedFileIds.length > 0 && (
        <div className="border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
          已有 {uploadedFileIds.length} 个文件附加到输入框
        </div>
      )}
    </div>
  );
}

/** 生成 mock 解析后的 Markdown 内容 */
function generateMockParsedMarkdown(fileName: string): string {
  return [
    `# ${fileName}`,
    "",
    "## 文档解析结果（Mock）",
    "",
    "> 该内容为前端 mock 阶段生成的占位解析结果，二阶段将接入真实文档解析服务。",
    "",
    "### 摘要",
    "",
    "- 文档类型：医疗相关文档",
    "- 关键信息：包含患者基本信息、症状描述、用药记录等",
    "- 建议结合上下文进一步分析",
    "",
    "### 关键段落",
    "",
    "1. **主诉**：患者近期出现血压波动，伴头晕乏力",
    "2. **现病史**：高血压病史 10 年，近 1 月控制欠佳",
    "3. **用药**：氨氯地平 5mg qd、二甲双胍 0.5g bid",
    "",
    "```",
    "注：医疗免责声明——本内容由 AI 生成，仅供参考，身体不适请及时就医。",
    "```",
  ].join("\n");
}
