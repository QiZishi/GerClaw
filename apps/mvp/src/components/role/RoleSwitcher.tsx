"use client";

import { useState } from "react";
import {
  Loader2,
  RefreshCw,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
import type { Role } from "@/types";

interface RoleSwitcherProps {
  /** 紧凑模式：仅显示图标按钮 */
  compact?: boolean;
  className?: string;
  /** 是否在切换后刷新页面（默认 false，避免开发体验中断） */
  reloadOnSwitch?: boolean;
}

/**
 * §角色切换 角色切换按钮 + 确认对话框
 * 对齐 design-docs/角色切换.md §2.3 角色切换完整流程
 * 流程：点击 → 弹确认 → 用户确认 → 调用 setRole → 可选 reload
 *
 * 严格 mock：不调用真实后端，仅修改 appStore.role
 */
export function RoleSwitcher({
  compact,
  className,
  reloadOnSwitch = false,
}: RoleSwitcherProps) {
  const role = useAppStore((s) => s.role);
  const setRole = useAppStore((s) => s.setRole);
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  const targetRole: Role = role === "doctor" ? "patient" : "doctor";
  const TargetIcon = targetRole === "doctor" ? Stethoscope : UserRound;
  const CurrentIcon = role === "doctor" ? Stethoscope : UserRound;

  const handleConfirm = () => {
    setSwitching(true);
    // 模拟切换延迟（避免瞬时闪烁）
    setTimeout(() => {
      setRole(targetRole);
      setSwitching(false);
      setOpen(false);
      if (reloadOnSwitch && typeof window !== "undefined") {
        window.location.reload();
      }
    }, 500);
  };

  if (compact) {
    return (
      <>
        <Button
          variant="ghost"
          size="icon"
          className={cn("btn-icon", className)}
          onClick={() => setOpen(true)}
          aria-label={`切换到${targetRole === "doctor" ? "医生端" : "患者端"}`}
        >
          <TargetIcon className="size-4" />
        </Button>
        <ConfirmDialog
          open={open}
          onOpenChange={setOpen}
          role={role}
          targetRole={targetRole}
          switching={switching}
          onConfirm={handleConfirm}
        />
      </>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "flex items-center gap-2 w-full rounded-lg border border-border bg-card px-3 py-2 hover:bg-muted/50 transition-colors text-left",
          className
        )}
        aria-label={`切换到${targetRole === "doctor" ? "医生端" : "患者端"}`}
      >
        <div
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-md",
            role === "doctor"
              ? "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
              : "bg-primary/10 text-primary"
          )}
        >
          <CurrentIcon className="size-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">
            {role === "doctor" ? "医生端" : "患者端"}
          </div>
          <div className="text-xs text-muted-foreground">
            点击切换到{targetRole === "doctor" ? "医生" : "患者"}模式
          </div>
        </div>
        <RefreshCw className="size-3.5 text-muted-foreground shrink-0" />
      </button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        role={role}
        targetRole={targetRole}
        switching={switching}
        onConfirm={handleConfirm}
      />
    </>
  );
}

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  role: Role;
  targetRole: Role;
  switching: boolean;
  onConfirm: () => void;
}

function ConfirmDialog({
  open,
  onOpenChange,
  role,
  targetRole,
  switching,
  onConfirm,
}: ConfirmDialogProps) {
  const isSwitchingToDoctor = targetRole === "doctor";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isSwitchingToDoctor ? (
              <Stethoscope className="size-4 text-blue-600" />
            ) : (
              <UserRound className="size-4 text-primary" />
            )}
            切换到{isSwitchingToDoctor ? "医生端" : "患者端"}
          </DialogTitle>
          <DialogDescription>
            切换后将更新界面布局与可用功能。
            {!isSwitchingToDoctor && (
              <>
                患者端默认开启
                <span className="font-medium text-foreground">老年模式</span>
                以提供适老化体验。
              </>
            )}
            {isSwitchingToDoctor && (
              <>
                医生端将
                <span className="font-medium text-foreground">关闭老年模式</span>
                ，启用标准医学界面。
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-md border border-border bg-muted/40 p-2.5 text-xs space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">当前角色</span>
            <Badge variant="outline">
              {role === "doctor" ? "医生端" : "患者端"}
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">目标角色</span>
            <Badge variant="default">
              {targetRole === "doctor" ? "医生端" : "患者端"}
            </Badge>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={switching}
          >
            取消
          </Button>
          <Button
            variant="default"
            onClick={onConfirm}
            disabled={switching}
            className="gap-1.5"
          >
            {switching ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            确认切换
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
