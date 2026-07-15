"use client";

import { Sparkles, Workflow, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SkillInfo } from "@/services/gerclaw/schemas";
import { useAppStore } from "@/stores/appStore";

interface SkillTagProps {
  skill: Pick<SkillInfo, "skill_id" | "name" | "source">;
  /** 是否可关闭（已加载状态下显示 × 按钮） */
  removable?: boolean;
  /** 关闭回调 */
  onRemove?: (id: string) => void;
  /** 点击标签本体回调 */
  onClick?: (id: string) => void;
  className?: string;
}

/**
 * §3.4 输入框标签区域 · 技能标签
 * 胶囊式徽章：技能图标 + 名称 + （可选）× 移除按钮
 * 预置技能与自定义技能配色区分（自定义技能附加紫色边）
 */
export function SkillTag({
  skill,
  removable,
  onRemove,
  onClick,
  className,
}: SkillTagProps) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isCustom = skill.source === "custom";
  const Icon = isCustom ? Sparkles : Workflow;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs transition-colors",
        seniorMode && "min-h-12 gap-2 px-3 text-lg",
        isCustom
          ? "bg-purple-50 text-purple-700 dark:bg-purple-950/30 dark:text-purple-300"
          : "bg-primary/10 text-primary",
        onClick && "cursor-pointer hover:opacity-80",
        className
      )}
      onClick={onClick ? () => onClick(skill.skill_id) : undefined}
      data-skill-id={skill.skill_id}
    >
      <Icon className={cn("size-3 shrink-0", seniorMode && "size-5")} aria-hidden />
      <span className="max-w-[160px] truncate">{skill.name}</span>
      {removable && onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(skill.skill_id);
          }}
          className={cn(
            "inline-flex items-center justify-center rounded-full hover:bg-foreground/15",
            seniorMode ? "min-h-12 min-w-12 gap-1.5 px-3 text-lg" : "size-3.5",
            isCustom
              ? "hover:bg-purple-700/20"
              : "hover:bg-primary/20"
          )}
          aria-label={`移除技能 ${skill.name}`}
        >
          <X className={cn("size-2.5", seniorMode && "size-5")} aria-hidden="true" />
          {seniorMode && <span>移除</span>}
        </button>
      )}
    </span>
  );
}
