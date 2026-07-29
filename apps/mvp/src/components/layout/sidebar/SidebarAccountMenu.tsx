"use client";

import {
  ArrowLeftRight,
  Copy,
  HelpCircle,
  History,
  LogOut,
  Moon,
  Settings,
  ShieldCheck,
  Stethoscope,
  Sun,
  Trash2,
  User,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { AccountIdentity } from "@/services/account";
import type { Role } from "@/types";

export interface SidebarAccountMenuActions {
  openAccount: () => void;
  setSeniorMode: (enabled: boolean) => void;
  toggleTheme: () => void;
  openHistory: () => void;
  openSettings: () => void;
  openHelp: () => void;
  openPrescriptionAccess: () => void;
  copyPatientCode: () => void;
  openPatientDirectory: () => void;
  openHealthProfile: () => void;
  openRuntimeApproval: () => void;
  openPrescriptionReview: () => void;
  openMedicationReview: () => void;
  openRiskAlerts: () => void;
  openChronicCare: () => void;
  openCgaWorkspace: () => void;
  copyDoctorCode: () => void;
  openAdminConsole: () => void;
  openPatientWorkspace: () => void;
  openDoctorWorkspace: () => void;
  deactivateAccount: () => void;
  exit: () => void;
}

interface SidebarAccountMenuProps {
  account: AccountIdentity | null;
  role: Role;
  isGuest: boolean;
  seniorMode: boolean;
  resolvedTheme: "light" | "dark";
  sessionCount: number;
  actions: SidebarAccountMenuActions;
}

export function SidebarAccountMenu({
  account,
  role,
  isGuest,
  seniorMode,
  resolvedTheme,
  sessionCount,
  actions,
}: SidebarAccountMenuProps) {
  const isPatient = role === "patient";
  const isDoctor = role === "doctor";
  const isAdministrator = account?.account_role === "admin";
  const menuItemClass = cn(
    "cursor-pointer",
    seniorMode && "min-h-12 text-base",
  );

  return (
    <div className="px-3 py-2">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <button
              type="button"
              className={cn(
                "flex w-full items-center gap-2 rounded-lg p-1.5 transition-colors hover:bg-sidebar-accent",
                seniorMode && "min-h-14 px-2 py-2 text-lg",
              )}
              aria-label="用户菜单"
            />
          }
        >
          <Avatar size="default" className="shrink-0">
            <AvatarFallback>
              {isDoctor ? (
                <Stethoscope className="size-4" />
              ) : (
                <User className="size-4" />
              )}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1 text-left">
            <div
              className={cn(
                "truncate text-sm font-medium",
                seniorMode && "text-lg",
              )}
            >
              {account ? "已登录账户" : isGuest ? "本次使用" : "未登录"}
            </div>
            <div
              className={cn(
                "truncate text-xs text-muted-foreground",
                seniorMode && "text-base",
              )}
            >
              {isDoctor ? "医生模式" : "患者模式"}
            </div>
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className={cn("w-60", seniorMode && "w-72 text-base")}
        >
          <DropdownMenuGroup>
            <DropdownMenuLabel>
              {account ? "账户身份由服务端验证" : "本次使用"}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          {!account && (
            <>
              <DropdownMenuItem
                className={menuItemClass}
                onClick={actions.openAccount}
              >
                <User className="size-4" />
                登录或创建账户
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>
          )}
          {isPatient && (
            <div
              className={cn(
                "flex items-center justify-between px-2 py-1.5 text-sm",
                seniorMode && "min-h-12 text-base",
              )}
            >
              <span>老年模式</span>
              <Switch
                checked={seniorMode}
                onCheckedChange={actions.setSeniorMode}
                aria-label="切换老年模式"
              />
            </div>
          )}
          <DropdownMenuItem
            onClick={actions.toggleTheme}
            className={cn(
              "flex cursor-pointer items-center justify-between",
              seniorMode && "min-h-12 text-base",
            )}
          >
            <span className="flex items-center gap-2">
              {resolvedTheme === "dark" ? (
                <Sun className="size-4" />
              ) : (
                <Moon className="size-4" />
              )}
              主题
            </span>
            <span
              className={cn(
                "text-xs text-muted-foreground",
                seniorMode && "text-base",
              )}
            >
              {resolvedTheme === "dark" ? "深色" : "浅色"}
            </span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            {isPatient && sessionCount > 0 && (
              <MenuItem
                className={menuItemClass}
                icon={History}
                onClick={actions.openHistory}
              >
                对话记录
              </MenuItem>
            )}
            <MenuItem className={menuItemClass} icon={Settings} onClick={actions.openSettings}>
              设置
            </MenuItem>
            <MenuItem className={menuItemClass} icon={HelpCircle} onClick={actions.openHelp}>
              帮助
            </MenuItem>
            {account?.account_role === "patient" && (
              <>
                <MenuItem className={menuItemClass} icon={ShieldCheck} onClick={actions.openPrescriptionAccess}>
                  医生资料授权
                </MenuItem>
                <MenuItem className={menuItemClass} icon={Copy} onClick={actions.copyPatientCode}>
                  复制我的患者代码
                </MenuItem>
              </>
            )}
            {account?.account_role === "doctor" && (
              <>
                <MenuItem className={menuItemClass} icon={User} onClick={actions.openPatientDirectory}>患者列表</MenuItem>
                <MenuItem className={menuItemClass} icon={User} onClick={actions.openHealthProfile}>患者健康画像</MenuItem>
                <MenuItem className={menuItemClass} icon={ShieldCheck} onClick={actions.openRuntimeApproval}>操作授权复核</MenuItem>
                <MenuItem className={menuItemClass} icon={ShieldCheck} onClick={actions.openPrescriptionReview}>五大处方草案复核</MenuItem>
                <MenuItem className={menuItemClass} icon={Stethoscope} onClick={actions.openMedicationReview}>用药审查记录</MenuItem>
                <MenuItem className={menuItemClass} icon={ShieldCheck} onClick={actions.openRiskAlerts}>患者安全提醒</MenuItem>
                <MenuItem className={menuItemClass} icon={Stethoscope} onClick={actions.openChronicCare}>患者慢病记录</MenuItem>
                <MenuItem className={menuItemClass} icon={Stethoscope} onClick={actions.openCgaWorkspace}>CGA 报告工作区</MenuItem>
                <MenuItem className={menuItemClass} icon={Copy} onClick={actions.copyDoctorCode}>复制我的复核代码</MenuItem>
              </>
            )}
          </DropdownMenuGroup>
          {isAdministrator && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <MenuItem className={menuItemClass} icon={ShieldCheck} onClick={actions.openAdminConsole}>管理控制台</MenuItem>
                {role !== "patient" && (
                  <MenuItem className={menuItemClass} icon={ArrowLeftRight} onClick={actions.openPatientWorkspace}>切换到患者端</MenuItem>
                )}
                {role !== "doctor" && (
                  <MenuItem className={menuItemClass} icon={ArrowLeftRight} onClick={actions.openDoctorWorkspace}>切换到医生端</MenuItem>
                )}
              </DropdownMenuGroup>
            </>
          )}
          <DropdownMenuSeparator />
          {account && (
            <>
              <MenuItem
                className={cn(menuItemClass, "text-destructive focus:text-destructive")}
                icon={Trash2}
                onClick={actions.deactivateAccount}
              >
                停用账户
              </MenuItem>
              <DropdownMenuSeparator />
            </>
          )}
          <MenuItem className={menuItemClass} icon={LogOut} onClick={actions.exit}>
            {account ? "退出账户" : "结束本次使用"}
          </MenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function MenuItem({
  icon: Icon,
  className,
  onClick,
  children,
}: {
  icon: typeof User;
  className: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <DropdownMenuItem className={className} onClick={onClick}>
      <Icon className="size-4" />
      {children}
    </DropdownMenuItem>
  );
}
