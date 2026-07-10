"use client";

import { useState } from "react";
import {
  Loader2,
  RefreshCw,
  Stethoscope,
  UserRound,
  Users,
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
  compact?: boolean;
  className?: string;
  reloadOnSwitch?: boolean;
}

function getRoleLabel(role: Role) {
  switch (role) {
    case "doctor":
      return "医生端";
    case "patient":
      return "患者端";
    case "visitor":
    default:
      return "访客端";
  }
}

function getRoleDescription(role: Role) {
  switch (role) {
    case "doctor":
      return "专业医学界面，适用于老年科医生";
    case "patient":
      return "适老化界面，适合老年朋友使用";
    case "visitor":
    default:
      return "了解平台功能，选择适合您的模式";
  }
}

function RoleIcon({ role, className }: { role: Role; className?: string }) {
  switch (role) {
    case "doctor":
      return <Stethoscope className={className} />;
    case "patient":
      return <UserRound className={className} />;
    case "visitor":
    default:
      return <Users className={className} />;
  }
}

export function RoleSwitcher({
  compact,
  className,
  reloadOnSwitch = false,
}: RoleSwitcherProps) {
  const role = useAppStore((s) => s.role);
  const setRole = useAppStore((s) => s.setRole);
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);

  const handleSelectRole = (targetRole: Role) => {
    if (targetRole === role) {
      setOpen(false);
      return;
    }
    setSelectedRole(targetRole);
  };

  const handleConfirm = () => {
    if (!selectedRole) return;
    setSwitching(true);
    setTimeout(() => {
      setRole(selectedRole);
      setSwitching(false);
      setSelectedRole(null);
      setOpen(false);
      if (reloadOnSwitch && typeof window !== "undefined") {
        window.location.reload();
      }
    }, 500);
  };

  const handleOpenChange = (openState: boolean) => {
    setOpen(openState);
    if (!openState) {
      setSelectedRole(null);
    }
  };

  if (compact) {
    return (
      <>
        <Button
          variant="ghost"
          size="icon"
          className={cn("btn-icon", className)}
          onClick={() => setOpen(true)}
          aria-label={`切换角色，当前${getRoleLabel(role)}`}
        >
          <RoleIcon role={role} className="size-4" />
        </Button>
        <RoleSelectDialog
          open={open}
          onOpenChange={handleOpenChange}
          currentRole={role}
          selectedRole={selectedRole}
          switching={switching}
          onSelectRole={handleSelectRole}
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
        aria-label={`切换角色，当前${getRoleLabel(role)}`}
      >
        <div
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-md",
            role === "doctor"
              ? "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
              : role === "patient"
              ? "bg-primary/10 text-primary"
              : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          <RoleIcon role={role} className="size-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">
            {getRoleLabel(role)}
          </div>
          <div className="text-xs text-muted-foreground">
            点击切换角色模式
          </div>
        </div>
        <RefreshCw className="size-3.5 text-muted-foreground shrink-0" />
      </button>
      <RoleSelectDialog
        open={open}
        onOpenChange={handleOpenChange}
        currentRole={role}
        selectedRole={selectedRole}
        switching={switching}
        onSelectRole={handleSelectRole}
        onConfirm={handleConfirm}
      />
    </>
  );
}

interface RoleSelectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentRole: Role;
  selectedRole: Role | null;
  switching: boolean;
  onSelectRole: (role: Role) => void;
  onConfirm: () => void;
}

function RoleSelectDialog({
  open,
  onOpenChange,
  currentRole,
  selectedRole,
  switching,
  onSelectRole,
  onConfirm,
}: RoleSelectDialogProps) {
  const roles: Role[] = ["visitor", "patient", "doctor"];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="size-4" />
            选择角色模式
          </DialogTitle>
          <DialogDescription>
            选择适合您的使用模式，切换后将更新界面布局与可用功能。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          {roles.map((r) => {
            const isCurrent = r === currentRole;
            const isSelected = r === selectedRole;
            return (
              <button
                key={r}
                type="button"
                onClick={() => onSelectRole(r)}
                disabled={isCurrent || switching}
                className={cn(
                  "w-full flex items-center gap-3 rounded-lg border p-3 text-left transition-all",
                  isCurrent
                    ? "border-border bg-muted/30 opacity-60 cursor-not-allowed"
                    : isSelected
                    ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                    : "border-border hover:border-primary/50 hover:bg-muted/50 cursor-pointer"
                )}
              >
                <div
                  className={cn(
                    "flex size-10 shrink-0 items-center justify-center rounded-lg",
                    r === "doctor"
                      ? "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
                      : r === "patient"
                      ? "bg-primary/10 text-primary"
                      : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                  )}
                >
                  <RoleIcon role={r} className="size-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{getRoleLabel(r)}</span>
                    {isCurrent && (
                      <Badge variant="secondary" className="text-xs">
                        当前
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {getRoleDescription(r)}
                  </div>
                  {r === "patient" && !isCurrent && (
                    <div className="text-xs text-primary mt-1">
                      将自动开启老年模式
                    </div>
                  )}
                  {r === "doctor" && !isCurrent && (
                    <div className="text-xs text-blue-600 mt-1">
                      将关闭老年模式，启用专业界面
                    </div>
                  )}
                </div>
              </button>
            );
          })}
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
            disabled={!selectedRole || switching}
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
