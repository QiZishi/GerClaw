"use client";

import type { DragEventHandler } from "react";

import { ComposerAttachmentTray } from "@/components/chat/composer/ComposerAttachmentTray";
import { ComposerToolbar } from "@/components/chat/composer/ComposerToolbar";
import { ComposerSubmitControl } from "@/components/chat/composer/ComposerSubmitControl";
import type { ComposerInputPanelProps } from "@/components/chat/composer/input-panel-types";
import { COMPOSER_FILE_ACCEPT } from "@/components/chat/composer/useComposerAttachments";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ALLOWED_IMAGE_MIME_TYPES, MEDICAL_DISCLAIMER } from "@/lib/constants";
import { cn } from "@/lib/utils";
export function ComposerInputPanel({
  text,
  placeholder,
  role,
  seniorMode,
  mounted,
  isOnline,
  asrAvailable,
  isGenerating,
  isSending,
  directiveSubmitting,
  isTranscribing,
  contextLoading,
  companionMode,
  prescriptionConversation,
  showMedicalDisclaimer,
  micDisabled,
  dragActive,
  hasUnboundParsedDocuments,
  pendingImages,
  pendingDocuments,
  loadedSkillIds,
  availableSkills,
  selectedCapabilityIds,
  limitDialogMessage,
  bindTextarea,
  bindImageInput,
  bindFileInput,
  onPickImage,
  onPickFile,
  onInput,
  onKeyDown,
  onPasteFiles,
  onAddImages,
  onAddFiles,
  onDragActiveChange,
  onCancelDocument,
  onRetryDocument,
  onRemoveDocument,
  onRemoveImage,
  onRemoveSkill,
  onCapabilityChange,
  onAction,
  onSend,
  onStop,
  onQueue,
  onSteer,
  onMicStart,
  onCancelTranscription,
  onLimitDialogChange,
}: ComposerInputPanelProps) {
  const handleDragEnter: DragEventHandler<HTMLDivElement> = (event) => {
    if (companionMode || !event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    onDragActiveChange(true);
  };
  const handleDragOver: DragEventHandler<HTMLDivElement> = (event) => {
    if (companionMode || !event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };
  const handleDragLeave: DragEventHandler<HTMLDivElement> = (event) => {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    onDragActiveChange(false);
  };
  const handleDrop: DragEventHandler<HTMLDivElement> = (event) => {
    if (companionMode) return;
    event.preventDefault();
    onDragActiveChange(false);
    onAddFiles(Array.from(event.dataTransfer.files));
  };
  const canSend =
    Boolean(text.trim()) ||
    (pendingImages.length > 0 && !hasUnboundParsedDocuments);
  const inputPlaceholder = isTranscribing
    ? seniorMode ? "正在识别语音…" : "识别中…"
    : hasUnboundParsedDocuments
      ? seniorMode ? "请说出您想了解的问题…" : "请输入您想了解的问题…"
      : placeholder;

  return (
    <div
      className={cn(
        "relative border-t border-border bg-background px-4 py-3",
        dragActive && !companionMode && "bg-primary/5",
      )}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {dragActive && !companionMode && (
        <div
          className="pointer-events-none absolute inset-2 z-20 grid place-items-center rounded-xl border-2 border-dashed border-primary bg-background/95 text-base font-medium text-primary"
          role="status"
        >
          松开即可添加到本次对话
        </div>
      )}
      <div className="mx-auto max-w-3xl">
        {!companionMode && (
          <ComposerAttachmentTray
            documents={pendingDocuments}
            images={pendingImages}
            loadedSkillIds={loadedSkillIds}
            availableSkills={availableSkills}
            seniorMode={seniorMode}
            onCancelDocument={onCancelDocument}
            onRetryDocument={onRetryDocument}
            onRemoveDocument={onRemoveDocument}
            onRemoveImage={onRemoveImage}
            onRemoveSkill={onRemoveSkill}
          />
        )}
        {!companionMode && hasUnboundParsedDocuments && (
          <p
            className={cn(
              "mb-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-muted-foreground",
              seniorMode ? "text-lg leading-8" : "text-sm",
            )}
            role="status"
          >
            资料已解析，发送即可。
          </p>
        )}
        {!companionMode && (
          <>
            <input
              ref={bindImageInput}
              type="file"
              accept={ALLOWED_IMAGE_MIME_TYPES.join(",")}
              multiple
              className="hidden"
              onChange={(event) => {
                onAddImages(Array.from(event.currentTarget.files ?? []));
                event.currentTarget.value = "";
              }}
            />
            <input
              ref={bindFileInput}
              type="file"
              accept={COMPOSER_FILE_ACCEPT}
              multiple
              className="hidden"
              onChange={(event) => {
                onAddFiles(Array.from(event.currentTarget.files ?? []));
                event.currentTarget.value = "";
              }}
            />
          </>
        )}
        <div className="rounded-xl border border-border bg-muted/50 transition-[border-color,box-shadow,background-color] duration-[var(--motion-popover)] ease-[var(--motion-ease-out)] focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring/40">
          <textarea
            ref={bindTextarea}
            value={text}
            onChange={onInput}
            onKeyDown={onKeyDown}
            onPaste={(event) => {
              if (companionMode) return;
              const files = Array.from(event.clipboardData.files);
              if (files.length === 0) return;
              event.preventDefault();
              onPasteFiles(files);
            }}
            placeholder={inputPlaceholder}
            rows={1}
            disabled={isTranscribing || contextLoading || isSending}
            className={cn(
              "max-h-[200px] min-h-[52px] w-full resize-none overflow-y-auto border-0 bg-transparent px-4 py-3 text-base leading-relaxed outline-none placeholder:text-muted-foreground disabled:opacity-60",
              seniorMode && "text-lg",
            )}
          />
          <div className="flex items-end justify-between gap-2 border-t border-border/60 px-2 py-1.5">
            {companionMode ? (
              <p className={cn("px-2 text-muted-foreground", seniorMode ? "text-base" : "text-xs")}>
                仅使用当前对话，不读取健康档案、资料或技能
              </p>
            ) : (
              <ComposerToolbar
                disabled={
                  isGenerating ||
                  isTranscribing ||
                  contextLoading ||
                  isSending
                }
                role={role}
                mounted={mounted}
                seniorMode={seniorMode}
                onAction={onAction}
                onPickImage={onPickImage}
                onPickFile={onPickFile}
                prescriptionConversation={prescriptionConversation}
                selectedCapabilityIds={selectedCapabilityIds}
                onCapabilityChange={onCapabilityChange}
              />
            )}
            <ComposerSubmitControl
              isGenerating={isGenerating}
              isTranscribing={isTranscribing}
              isSending={isSending}
              directiveSubmitting={directiveSubmitting}
              hasDirectiveText={Boolean(text.trim())}
              canSend={canSend}
              isOnline={isOnline}
              asrAvailable={asrAvailable}
              micDisabled={micDisabled}
              seniorMode={seniorMode}
              onSend={onSend}
              onStop={onStop}
              onQueue={onQueue}
              onSteer={onSteer}
              onMicStart={onMicStart}
              onCancelTranscription={onCancelTranscription}
            />
          </div>
        </div>
        {(contextLoading || companionMode || showMedicalDisclaimer) && (
          <div className={cn("mt-1.5 text-muted-foreground", seniorMode ? "text-lg" : "text-[11px]")}>
            {contextLoading && (
              <span role="status" className={cn("mb-1 block text-primary", seniorMode && "text-lg")}>
                正在恢复当前会话的技能，恢复完成后即可发送。
              </span>
            )}
            {companionMode
              ? "此模式提供情感支持，不替代医疗咨询、心理治疗或紧急援助。"
              : showMedicalDisclaimer
                ? MEDICAL_DISCLAIMER
                : null}
          </div>
        )}
      </div>
      <Dialog
        open={limitDialogMessage !== null}
        onOpenChange={(open) => {
          if (!open) onLimitDialogChange(null);
        }}
      >
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader><DialogTitle>提示</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">{limitDialogMessage ?? ""}</p>
          <DialogFooter>
            <DialogClose render={<Button variant="outline">我知道了</Button>} />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
