"use client";

import { useState } from "react";
import {
  Check,
  Edit3,
  Eye,
  Loader2,
  Save,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";

export type PrescriptionStatus =
  | "draft"
  | "editing"
  | "approved"
  | "rejected";

export interface PrescriptionReview {
  status: PrescriptionStatus;
  reviewedAt?: number;
  reviewedBy?: string;
  rejectReason?: string;
}

interface ApprovalBarProps {
  status: PrescriptionStatus;
  onStatusChange?: (review: PrescriptionReview) => void;
  onEdit?: () => void;
  onSave?: () => void;
  onCancelEdit?: () => void;
  className?: string;
}

/**
 * §医生端 处方审核操作条
 * 不同状态下显示不同按钮：
 * - draft: [编辑] [驳回] [审核通过]
 * - editing: [取消] [保存]
 * - approved: [查看已审核处方] (不可改)
 * - rejected: [重新编辑]
 *
 * 严格 mock：所有操作仅本地 state + setTimeout 模拟审核
 */
export function ApprovalBar({
  status,
  onStatusChange,
  onEdit,
  onSave,
  onCancelEdit,
  className,
}: ApprovalBarProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [approving, setApproving] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2000);
  };

  const handleApprove = () => {
    setApproving(true);
    setTimeout(() => {
      setApproving(false);
      onStatusChange?.({
        status: "approved",
        reviewedAt: Date.now(),
        reviewedBy: "Dr. Wang（mock）",
      });
      showToast("处方已审核通过");
    }, 800);
  };

  const handleReject = () => {
    onStatusChange?.({
      status: "rejected",
      reviewedAt: Date.now(),
      reviewedBy: "Dr. Wang（mock）",
      rejectReason: rejectReason.trim() || "未填写驳回原因",
    });
    setRejectReason("");
    setRejectOpen(false);
    showToast("处方已驳回");
  };

  return (
    <div
      className={cn(
        "border-t border-border bg-background px-3 py-2 flex items-center justify-between gap-2",
        seniorMode && "py-3",
        className
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        <StatusBadge status={status} />
        {toast && (
          <span
            role="status"
            aria-live="polite"
            className="text-xs text-muted-foreground truncate"
          >
            {toast}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        {status === "draft" && (
          <>
            <Button
              variant="outline"
              size="sm"
              className="gap-1"
              onClick={onEdit}
            >
              <Edit3 className="size-3.5" />
              编辑
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1 text-destructive hover:text-destructive"
              onClick={() => setRejectOpen(true)}
            >
              <X className="size-3.5" />
              驳回
            </Button>
            <Button
              variant="default"
              size="sm"
              className="gap-1"
              onClick={handleApprove}
              disabled={approving}
            >
              {approving ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Check className="size-3.5" />
              )}
              审核通过
            </Button>
          </>
        )}

        {status === "editing" && (
          <>
            <Button
              variant="outline"
              size="sm"
              className="gap-1"
              onClick={onCancelEdit}
            >
              取消
            </Button>
            <Button
              variant="default"
              size="sm"
              className="gap-1"
              onClick={onSave}
            >
              <Save className="size-3.5" />
              保存
            </Button>
          </>
        )}

        {status === "approved" && (
          <Button
            variant="outline"
            size="sm"
            className="gap-1 text-green-700 dark:text-green-400"
            disabled
          >
            <Eye className="size-3.5" />
            已审核
          </Button>
        )}

        {status === "rejected" && (
          <Button
            variant="default"
            size="sm"
            className="gap-1"
            onClick={onEdit}
          >
            <Edit3 className="size-3.5" />
            重新编辑
          </Button>
        )}
      </div>

      {/* 驳回原因 Dialog */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>驳回处方</DialogTitle>
            <DialogDescription>
              请填写驳回原因（可选），将记录到处方审核历史。
            </DialogDescription>
          </DialogHeader>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="例如：药物剂量需调整、缺少循证依据…"
            rows={4}
            maxLength={200}
            className="text-xs w-full rounded-lg border border-input bg-transparent px-2.5 py-1 outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleReject}
            >
              确认驳回
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatusBadge({ status }: { status: PrescriptionStatus }) {
  const map: Record<
    PrescriptionStatus,
    { label: string; className: string }
  > = {
    draft: {
      label: "待审核",
      className: "bg-amber-100 text-amber-800 dark:bg-amber-950/30 dark:text-amber-300",
    },
    editing: {
      label: "编辑中",
      className: "bg-blue-100 text-blue-800 dark:bg-blue-950/30 dark:text-blue-300",
    },
    approved: {
      label: "已审核",
      className: "bg-green-100 text-green-800 dark:bg-green-950/30 dark:text-green-300",
    },
    rejected: {
      label: "已驳回",
      className: "bg-red-100 text-red-800 dark:bg-red-950/30 dark:text-red-300",
    },
  };
  const { label, className } = map[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        className
      )}
    >
      {label}
    </span>
  );
}
