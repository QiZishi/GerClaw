"use client";

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
          <DialogTitle>{props.type === "up" ? "点赞反馈" : "点踩反馈"}</DialogTitle>
        </DialogHeader>
        <textarea
          value={props.text}
          onChange={(event) => props.onTextChange(event.target.value)}
          placeholder="请输入您的评价（可选）"
          disabled={props.submitting}
          className={cn(
            "w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            props.seniorMode && "min-h-32 text-lg",
          )}
          rows={4}
        />
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
