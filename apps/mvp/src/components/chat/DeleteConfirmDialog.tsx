"use client";

import { useState } from "react";
import { Trash2, AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { Message } from "@/types";

interface DeleteConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  messages: Message[];
  defaultSelectedIds?: string[];
  onConfirm: (selectedIds: string[]) => void;
}

function getMessagePreview(msg: Message): string {
  const textBlock = msg.blocks.find((b) => b.kind === "text");
  if (textBlock && "content" in textBlock) {
    return textBlock.content.slice(0, 50) + (textBlock.content.length > 50 ? "..." : "");
  }
  return "[空消息]";
}

export function DeleteConfirmDialog({
  open,
  onOpenChange,
  messages,
  defaultSelectedIds = [],
  onConfirm,
}: DeleteConfirmDialogProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(defaultSelectedIds));

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectedMessages = messages.filter((m) => selectedIds.has(m.id));

  const handleConfirm = () => {
    onConfirm(Array.from(selectedIds));
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-5" />
            删除消息
          </DialogTitle>
          <DialogDescription>
            选择要删除的消息，删除后无法恢复。
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="border border-border rounded-lg divide-y divide-border max-h-64 overflow-y-auto">
            {messages.map((msg) => {
              const isSelected = selectedIds.has(msg.id);
              return (
                <label
                  key={msg.id}
                  className="flex items-start gap-3 p-3 hover:bg-muted/30 cursor-pointer transition-colors"
                >
                  <Checkbox
                    checked={isSelected}
                    onCheckedChange={() => toggleSelect(msg.id)}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span
                        className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                          msg.role === "user"
                            ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                            : "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
                        }`}
                      >
                        {msg.role === "user" ? "用户" : "AI"}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground truncate">
                      {getMessagePreview(msg)}
                    </p>
                  </div>
                </label>
              );
            })}
          </div>
        </div>

        <DialogFooter className="gap-2">
          <DialogClose render={<Button variant="outline" />}>
            取消
          </DialogClose>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={selectedMessages.length === 0}
          >
            <Trash2 className="size-4 mr-1" />
            确认删除 {selectedMessages.length > 0 ? `(${selectedMessages.length})` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
