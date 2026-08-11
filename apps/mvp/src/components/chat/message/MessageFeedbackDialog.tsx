"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface MessageFeedbackDialogProps {
  open: boolean;
  type: "up" | "down" | null;
  text: string;
  submitting: boolean;
  seniorMode: boolean;
  onOpenChange: (open: boolean) => void;
  onTextChange: (text: string) => void;
  onSubmit: () => void;
}

export function MessageFeedbackDialog(props: MessageFeedbackDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>
            {props.type === "up" ? "有帮助反馈" : "没帮助反馈"}
          </DialogTitle>
          <DialogDescription>
            可以补充原因，帮助我们改进回答；不填写也可以直接提交。
          </DialogDescription>
        </DialogHeader>
        <textarea
          value={props.text}
          onChange={(event) => props.onTextChange(event.target.value)}
          placeholder={
            props.type === "up"
              ? "请告诉我们哪些内容有帮助（可选）"
              : "请告诉我们哪里需要改进（可选）"
          }
          aria-label="反馈评论（可选）"
          disabled={props.submitting}
          maxLength={2_000}
          className={cn(
            "w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            props.seniorMode && "min-h-32 text-lg",
          )}
          rows={4}
        />
        <div
          className={cn(
            "text-right text-xs text-muted-foreground",
            props.seniorMode && "text-base",
          )}
        >
          {props.text.length} / 2000
        </div>
        <DialogFooter className="gap-2">
          <DialogClose
            render={
              <Button
                variant="outline"
                disabled={props.submitting}
                className={cn(props.seniorMode && "min-h-12 px-4 text-base")}
              >
                取消
              </Button>
            }
          />
          <Button
            className={cn(props.seniorMode && "min-h-12 px-4 text-base")}
            onClick={props.onSubmit}
            disabled={props.submitting}
          >
            {props.submitting ? "正在提交" : "提交反馈"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
