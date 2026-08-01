"use client";

import { AlertTriangle, Check, Copy, Loader2, RefreshCw } from "lucide-react";

import { useArtifactWorkspace } from "@/components/artifact/useArtifactWorkspace";
import { RichTextArtifactEditor } from "@/components/artifact/RichTextArtifactEditor";
import {
  artifactMarkdownToRichHtml,
  richHtmlToPlainText,
  sanitizeRichHtml,
} from "@/components/artifact/rich-text-document";
import { ExportButton } from "@/components/prescription/ExportButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import { useArtifactStore } from "@/stores/artifactStore";

const STATUS_LABELS = {
  creating: "正在建立安全文档",
  dirty: "等待自动保存",
  saving: "正在保存",
  saved: "已保存",
  "local-only": "仅保留在当前页面",
  error: "尚未保存",
  conflict: "版本冲突",
} as const;

export function ArtifactWorkspace() {
  const source = useArtifactStore((state) => state.source);
  if (!source) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="font-medium">还没有文档产物</p>
        <p className="max-w-sm text-sm leading-6 text-muted-foreground">
          在助手回答的“更多”菜单中选择“转为文档”。
        </p>
      </div>
    );
  }
  return <ArtifactEditor key={source.requestId} source={source} />;
}

function ArtifactEditor({
  source,
}: {
  source: NonNullable<ReturnType<typeof useArtifactStore.getState>["source"]>;
}) {
  const workspace = useArtifactWorkspace(source);
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isSeniorPatient = role === "patient" && seniorMode;
  const busy = workspace.status === "creating" || workspace.status === "saving";
  const saved = workspace.status === "saved";

  const copyDocument = async () => {
    try {
      const plainText = richHtmlToPlainText(
        artifactMarkdownToRichHtml(workspace.markdown),
      );
      await navigator.clipboard.writeText(plainText);
      toast.show("文档文字已复制");
    } catch {
      toast.show("复制失败，请手动选择文字");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={cn("shrink-0 space-y-3 border-b border-border p-4", isSeniorPatient && "p-5")}>
        <label className="block">
          <span className={cn("mb-1.5 block text-xs font-medium text-muted-foreground", isSeniorPatient && "text-base")}>
            文档标题
          </span>
          <Input
            value={workspace.title}
            onChange={(event) => workspace.setTitle(event.target.value)}
            maxLength={300}
            aria-invalid={!workspace.title.trim()}
            className={cn("font-medium", isSeniorPatient && "h-12 text-lg")}
          />
        </label>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div
            className={cn(
              "flex min-h-8 items-center gap-1.5 text-xs text-muted-foreground",
              isSeniorPatient && "min-h-12 text-base",
            )}
            role="status"
            aria-live="polite"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
            ) : saved ? (
              <Check className="size-4 text-green-700" aria-hidden />
            ) : (
              <AlertTriangle className="size-4 text-amber-700" aria-hidden />
            )}
            <span>{STATUS_LABELS[workspace.status]}</span>
            {workspace.artifact && <span>· 修订 {workspace.artifact.revision}</span>}
          </div>
          <div className={cn("flex flex-wrap items-center gap-2", isSeniorPatient && "[&_button]:min-h-12 [&_button]:text-base")}>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void copyDocument()}
              disabled={!workspace.markdown}
            >
              <Copy className="size-4" />
              复制文档
            </Button>
            <ExportButton
              title={workspace.title.trim() || "GerClaw 文档"}
              content={workspace.markdown}
              renderedHtml={sanitizeRichHtml(
                artifactMarkdownToRichHtml(workspace.markdown),
              )}
              formats={["docx", "pdf", "png", "jpg", "html"]}
              variant="dropdown"
            />
          </div>
        </div>

        {!source.runId && (
          <p className={cn("rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100", isSeniorPatient && "text-base leading-7")}>
            这条历史回答缺少 Run 标识，无法写入服务端。请在关闭前复制或导出。
          </p>
        )}
        {workspace.errorMessage && (
          <div className="flex items-start justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
            <p className={cn("text-xs leading-5 text-destructive", isSeniorPatient && "text-base leading-7")}>
              {workspace.errorMessage}
            </p>
            {source.runId && (
              <Button
                variant="outline"
                size="sm"
                className={cn("shrink-0 gap-1.5", isSeniorPatient && "min-h-12 text-base")}
                onClick={() => void workspace.retrySave()}
              >
                <RefreshCw className="size-4" />
                {workspace.status === "conflict" ? "基于最新版本重试" : "重试"}
              </Button>
            )}
          </div>
        )}
      </div>

      <RichTextArtifactEditor
        value={workspace.markdown}
        onChange={workspace.setMarkdown}
        className="min-h-0 flex-1"
        seniorMode={isSeniorPatient}
      />
    </div>
  );
}
