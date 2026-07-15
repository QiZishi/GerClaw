"use client";

import { Check, Eye, Loader2, LockKeyhole, Pencil, Power, Trash2, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { SkillInfo } from "@/services/gerclaw/schemas";
import { cn } from "@/lib/utils";

interface SkillCardProps {
  skill: SkillInfo;
  loaded: boolean;
  busy: boolean;
  seniorMode: boolean;
  onLoadToggle: () => void;
  onView: () => void;
  onEdit?: () => void;
  onEnabledChange?: (enabled: boolean) => void;
  onDelete?: () => void;
}

const TOOL_LABELS: Record<string, string> = {
  search_knowledge: "本地证据",
  search_memory: "健康记忆",
  web_search: "联网检索",
};

export function SkillCard({
  skill,
  loaded,
  busy,
  seniorMode,
  onLoadToggle,
  onView,
  onEdit,
  onEnabledChange,
  onDelete,
}: SkillCardProps) {
  const custom = skill.source === "custom";
  return (
    <li
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-card transition-colors",
        loaded ? "border-primary/45 bg-primary/[0.025]" : "border-border hover:border-foreground/20",
        !skill.enabled && "opacity-65"
      )}
    >
      <div className={cn("absolute inset-y-0 left-0 w-1", loaded ? "bg-primary" : "bg-border")} aria-hidden="true" />
      <div className="flex h-full flex-col gap-4 p-4 pl-5">
        <div className="flex items-start gap-3">
          <span className={cn("mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border", seniorMode && "size-12", loaded ? "border-primary/25 bg-primary/10 text-primary" : "border-border bg-muted/50 text-muted-foreground")}>
            <Workflow className={cn("size-4", seniorMode && "size-6")} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className={cn("font-semibold leading-6", seniorMode && "text-xl")}>{skill.name}</h3>
              <Badge variant="outline" className={cn("h-6 px-2 text-xs", seniorMode && "h-8 px-3 text-lg")}>
                {custom ? "自定义" : "系统"}
              </Badge>
            </div>
            <p className={cn("mt-1 line-clamp-2 text-sm leading-5 text-muted-foreground", seniorMode && "text-lg leading-7")}>
              {skill.description}
            </p>
          </div>
        </div>

        <div className="flex min-h-6 flex-wrap items-center gap-1.5">
          {skill.tool_names.length === 0 ? (
            <span className={cn("inline-flex items-center gap-1 text-xs text-muted-foreground", seniorMode && "text-lg")}>
              <LockKeyhole className={cn("size-3", seniorMode && "size-5")} aria-hidden="true" /> 无外部工具权限
            </span>
          ) : (
            skill.tool_names.map((tool) => (
              <Badge key={tool} variant="secondary" className={cn("font-normal", seniorMode && "min-h-8 px-3 text-lg")}>
                {TOOL_LABELS[tool] ?? tool}
              </Badge>
            ))
          )}
        </div>

        <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-3">
          <div className={cn("text-xs tabular-nums text-muted-foreground", seniorMode && "text-lg")}>
            v{skill.version} · rev {skill.revision}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onView}
              disabled={busy}
              className={cn(seniorMode && "h-12 px-3 text-lg")}
            >
              <Eye className={cn("size-4", seniorMode && "size-5")} aria-hidden="true" />
              查看
            </Button>
            {custom && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onEdit}
                  disabled={busy}
                  className={cn(seniorMode && "h-12 px-3 text-lg")}
                >
                  <Pencil className={cn("size-4", seniorMode && "size-5")} aria-hidden="true" />
                  编辑
                </Button>
                <label
                  htmlFor={`skill-enabled-${skill.skill_id}`}
                  className={cn(
                    "inline-flex cursor-pointer items-center gap-2 rounded-lg px-2 text-sm font-medium",
                    seniorMode && "min-h-12 text-lg"
                  )}
                >
                  <Switch
                    id={`skill-enabled-${skill.skill_id}`}
                    size={seniorMode ? "lg" : "default"}
                    checked={skill.enabled}
                    onCheckedChange={onEnabledChange}
                    disabled={busy}
                    aria-label={skill.enabled ? `停用${skill.name}` : `启用${skill.name}`}
                  />
                  {skill.enabled ? "已启用" : "已停用"}
                </label>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onDelete}
                  disabled={busy}
                  className={cn("text-destructive hover:text-destructive", seniorMode && "h-12 px-3 text-lg")}
                >
                  <Trash2 className={cn("size-4", seniorMode && "size-5")} aria-hidden="true" />
                  删除
                </Button>
              </>
            )}
            <Button
              variant={loaded ? "secondary" : "outline"}
              size="sm"
              onClick={onLoadToggle}
              disabled={busy || !skill.enabled}
              className={cn("min-w-24", seniorMode && "h-12 min-w-32 px-4 text-lg")}
            >
              {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : loaded ? <Check className="size-4" aria-hidden="true" /> : <Power className="size-4" aria-hidden="true" />}
              {loaded ? "已加载" : "加载到对话"}
            </Button>
          </div>
        </div>
      </div>
    </li>
  );
}
