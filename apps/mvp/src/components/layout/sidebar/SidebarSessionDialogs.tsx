"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface SidebarSessionDialogsProps {
  seniorMode: boolean;
  isDoctor: boolean;
  renameTarget: Session | null;
  renameTitle: string;
  deleteTarget: Session | null;
  deletingSession: boolean;
  pendingRole: "patient" | "doctor" | null;
  onRenameTitleChange: (title: string) => void;
  onCloseRename: () => void;
  onConfirmRename: () => void;
  onCloseDelete: () => void;
  onConfirmDelete: () => void;
  onCloseRoleChange: () => void;
  onConfirmRoleChange: () => void;
}

export function SidebarSessionDialogs({
  seniorMode,
  isDoctor,
  renameTarget,
  renameTitle,
  deleteTarget,
  deletingSession,
  pendingRole,
  onRenameTitleChange,
  onCloseRename,
  onConfirmRename,
  onCloseDelete,
  onConfirmDelete,
  onCloseRoleChange,
  onConfirmRoleChange,
}: SidebarSessionDialogsProps) {
  const contentClass = cn("sm:max-w-md", seniorMode && "p-5");
  const titleClass = cn(seniorMode && "text-2xl");
  const descriptionClass = cn(seniorMode && "text-lg leading-8");
  const footerClass = cn(
    "mt-5",
    seniorMode && "flex-row justify-end gap-3 p-5",
  );
  const buttonClass = cn(seniorMode && "min-h-12 text-lg");

  return (
    <>
      <Dialog
        open={renameTarget !== null}
        onOpenChange={(open) => {
          if (!open) onCloseRename();
        }}
      >
        <DialogContent showCloseButton={!seniorMode} className={contentClass}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              onConfirmRename();
            }}
          >
            <DialogHeader>
              <DialogTitle className={titleClass}>
                {isDoctor ? "重命名病例会话" : "重命名对话"}
              </DialogTitle>
              <DialogDescription className={descriptionClass}>
                {isDoctor
                  ? "使用便于识别的名称，方便后续继续病例工作。"
                  : "使用容易识别的名称，方便下次继续咨询。"}
              </DialogDescription>
            </DialogHeader>
            <div className="mt-5">
              <Label
                htmlFor="session-title"
                className={cn(seniorMode && "text-lg")}
              >
                {isDoctor ? "病例会话名称" : "对话名称"}
              </Label>
              <Input
                id="session-title"
                autoFocus
                value={renameTitle}
                maxLength={80}
                onChange={(event) => onRenameTitleChange(event.target.value)}
                className={cn("mt-2", seniorMode && "h-12 text-lg")}
              />
            </div>
            <DialogFooter className={footerClass}>
              <Button
                type="button"
                variant="outline"
                className={buttonClass}
                onClick={onCloseRename}
              >
                取消
              </Button>
              <Button
                type="submit"
                className={buttonClass}
                disabled={!renameTitle.trim()}
              >
                保存名称
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) onCloseDelete();
        }}
      >
        <DialogContent showCloseButton={!seniorMode} className={contentClass}>
          <DialogHeader>
            <DialogTitle className={cn(titleClass, "text-destructive")}>
              {isDoctor ? "确认删除病例会话" : "确认删除对话"}
            </DialogTitle>
            <DialogDescription className={descriptionClass}>
              删除“{deleteTarget?.title}”后，其中的所有内容将无法恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className={footerClass}>
            <Button
              variant="outline"
              className={buttonClass}
              onClick={onCloseDelete}
              disabled={deletingSession}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              className={buttonClass}
              onClick={onConfirmDelete}
              disabled={deletingSession}
            >
              {deletingSession ? "正在删除…" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingRole !== null}
        onOpenChange={(open) => {
          if (!open) onCloseRoleChange();
        }}
      >
        <DialogContent showCloseButton={!seniorMode} className={contentClass}>
          <DialogHeader>
            <DialogTitle className={titleClass}>
              切换到
              {pendingRole === "doctor" ? "医生模式" : "患者模式"}
            </DialogTitle>
            <DialogDescription className={descriptionClass}>
              切换后会显示适合该身份的功能。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className={footerClass}>
            <Button
              variant="outline"
              className={buttonClass}
              onClick={onCloseRoleChange}
            >
              取消
            </Button>
            <Button className={buttonClass} onClick={onConfirmRoleChange}>
              确认切换
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
