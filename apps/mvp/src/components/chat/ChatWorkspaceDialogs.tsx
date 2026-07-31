"use client";

import { AlertTriangle } from "lucide-react";

import { ExportDialog } from "@/components/chat/ExportDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { Message } from "@/types";

export type ExitConfirmType =
  | "cga-server"
  | "clinical-intake"
  | "prescription";

interface ChatWorkspaceDialogsProps {
  messages: Message[];
  seniorMode: boolean;
  exportMessageId: string | null;
  deleteMessageId: string | null;
  showExitConfirm: boolean;
  exitConfirmType: ExitConfirmType;
  onCloseExport: () => void;
  onCloseDelete: () => void;
  onConfirmDelete: () => void;
  onExitOpenChange: (open: boolean) => void;
  onConfirmExit: () => void;
}

export function ChatWorkspaceDialogs({
  messages,
  seniorMode,
  exportMessageId,
  deleteMessageId,
  showExitConfirm,
  exitConfirmType,
  onCloseExport,
  onCloseDelete,
  onConfirmDelete,
  onExitOpenChange,
  onConfirmExit,
}: ChatWorkspaceDialogsProps) {
  const dialogContentClass = cn("max-w-sm", seniorMode && "p-5");
  const dialogTitleClass = cn(
    "flex items-center gap-2",
    seniorMode && "text-2xl",
  );
  const dialogBodyClass = cn(
    "text-muted-foreground",
    seniorMode ? "text-lg leading-8" : "text-sm",
  );
  const dialogFooterClass = cn(
    "gap-2",
    seniorMode && "flex-row justify-end gap-3 p-5",
  );
  const dialogButtonClass = cn(seniorMode && "min-h-12 px-4 text-lg");

  return (
    <>
      <ExportDialog
        key={exportMessageId ?? "closed"}
        open={exportMessageId !== null}
        onOpenChange={(open) => {
          if (!open) onCloseExport();
        }}
        messages={messages}
        defaultSelectedIds={exportMessageId ? [exportMessageId] : []}
      />

      <Dialog open={showExitConfirm} onOpenChange={onExitOpenChange}>
        <DialogContent className={dialogContentClass} showCloseButton={false}>
          <DialogHeader>
            <DialogTitle className={dialogTitleClass}>
              <AlertTriangle className="size-5 text-amber-500" />
              {exitConfirmType === "cga-server"
                ? "确认暂时休息？"
                : exitConfirmType === "clinical-intake"
                  ? "确认返回咨询？"
                  : "停止生成并返回？"}
            </DialogTitle>
          </DialogHeader>
          <p className={dialogBodyClass}>
            {exitConfirmType === "cga-server"
              ? "当前进度已安全保存。退出后，您下次可以从这道题继续。"
              : exitConfirmType === "clinical-intake"
                ? "本次已提交的信息会保留在当前会话。"
                : "已收集的信息会保留在当前会话。若草案正在生成，系统会先安全停止；未完成内容不会保存为草案。"}
          </p>
          <DialogFooter className={dialogFooterClass}>
            <DialogClose
              render={
                <Button variant="outline" className={dialogButtonClass}>
                  取消
                </Button>
              }
            />
            <Button
              variant="destructive"
              className={dialogButtonClass}
              onClick={onConfirmExit}
            >
              {exitConfirmType === "cga-server"
                ? "保存并休息"
                : exitConfirmType === "clinical-intake"
                  ? "返回咨询"
                  : "停止并返回"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteMessageId !== null}
        onOpenChange={(open) => {
          if (!open) onCloseDelete();
        }}
      >
        <DialogContent className={dialogContentClass} showCloseButton={false}>
          <DialogHeader>
            <DialogTitle className={dialogTitleClass}>
              <AlertTriangle className="size-5 text-amber-500" />
              确认删除消息
            </DialogTitle>
          </DialogHeader>
          <p className={dialogBodyClass}>删除后该条消息将无法恢复。</p>
          <DialogFooter className={dialogFooterClass}>
            <DialogClose
              render={
                <Button variant="outline" className={dialogButtonClass}>
                  取消
                </Button>
              }
            />
            <Button
              variant="destructive"
              className={dialogButtonClass}
              onClick={onConfirmDelete}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
