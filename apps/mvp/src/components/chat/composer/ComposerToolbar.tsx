"use client";

import {
  ClipboardCheck,
  FileSearch,
  ImageIcon,
  Paperclip,
  Pill,
  UserRound,
} from "lucide-react";

import { SkillSelector } from "@/components/skills/SkillSelector";
import { CapabilitySelector } from "@/components/chat/composer/CapabilitySelector";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Role } from "@/types";

export type ComposerAction = "prescription" | "cga" | "drug-review" | "health-profile";

interface ComposerToolbarProps {
  disabled: boolean;
  role: Role;
  mounted: boolean;
  seniorMode: boolean;
  prescriptionConversation: boolean;
  isGuest: boolean;
  selectedCapabilityIds: string[];
  onCapabilityChange: (ids: string[]) => void;
  onAction: (action: ComposerAction) => void;
  onPickImage: () => void;
  onPickFile: () => void;
}

export function ComposerToolbar({
  disabled,
  role,
  mounted,
  seniorMode,
  prescriptionConversation,
  isGuest,
  selectedCapabilityIds,
  onCapabilityChange,
  onAction,
  onPickImage,
  onPickFile,
}: ComposerToolbarProps) {
  const isDoctor = mounted && role === "doctor";
  return (
    <div
      className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto overscroll-x-contain pb-1"
      tabIndex={0}
      aria-label="对话工具，可横向滚动"
    >
      <ToolbarButton
        label="图片"
        tooltip="上传图片"
        seniorMode={seniorMode}
        disabled={disabled}
        order="order-1"
        onClick={onPickImage}
        icon={<ImageIcon className="size-4" aria-hidden />}
      />
      <ToolbarButton
        label="文件"
        tooltip="上传文件（PDF/DOCX/MD/图片）"
        seniorMode={seniorMode}
        disabled={disabled}
        order="order-2"
        onClick={onPickFile}
        icon={<Paperclip className="size-4" aria-hidden />}
      />
      {!isGuest && !prescriptionConversation && (
        <SkillSelector showLabel={seniorMode}>
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon"}
            className={cn("btn-icon shrink-0", seniorMode && "order-3 h-12 min-w-24 px-4 text-lg")}
            aria-label="选择当前对话的临床技能"
            disabled={disabled}
          />
        </SkillSelector>
      )}
      {!prescriptionConversation && (
        <CapabilitySelector
          selectedIds={selectedCapabilityIds}
          seniorMode={seniorMode}
          disabled={disabled}
          onChange={onCapabilityChange}
        />
      )}
      {!prescriptionConversation && (
        <>
          <ToolbarButton
            label="处方信息"
            tooltip="五大处方信息收集"
            seniorMode={seniorMode}
            disabled={disabled}
            order="order-4"
            onClick={() => onAction("prescription")}
            icon={<Pill className="size-4" aria-hidden />}
          />
          <ToolbarButton
            label="评估"
            tooltip="老年综合评估"
            seniorMode={seniorMode}
            disabled={disabled}
            order="order-5"
            onClick={() => onAction("cga")}
            icon={<ClipboardCheck className="size-4" aria-hidden />}
          />
        </>
      )}
      {!prescriptionConversation && isDoctor && (
        <ToolbarButton
          label="用药信息"
          tooltip="用药信息收集"
          seniorMode={seniorMode}
          disabled={disabled}
          order="order-6"
          onClick={() => onAction("drug-review")}
          icon={<FileSearch className="size-4" aria-hidden />}
        />
      )}
      {!prescriptionConversation && mounted && role === "patient" && (
        <ToolbarButton
          label="档案"
          tooltip="查看我的健康记录"
          seniorMode={seniorMode}
          disabled={disabled}
          order="order-7"
          onClick={() => onAction("health-profile")}
          icon={<UserRound className="size-4" aria-hidden />}
        />
      )}
    </div>
  );
}

function ToolbarButton({
  label,
  tooltip,
  seniorMode,
  disabled,
  order,
  onClick,
  icon,
}: {
  label: string;
  tooltip: string;
  seniorMode: boolean;
  disabled: boolean;
  order: string;
  onClick: () => void;
  icon: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon"}
            className={cn(
              "btn-icon shrink-0",
              seniorMode &&
                `${order} h-12 min-w-12 gap-1 px-2 text-base sm:gap-2 sm:px-3`,
            )}
            onClick={onClick}
            aria-label={tooltip}
            disabled={disabled}
          />
        }
      >
        {icon}
        {seniorMode && <span>{label}</span>}
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
