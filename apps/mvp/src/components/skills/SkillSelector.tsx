"use client";

import { useMemo, useState } from "react";
import { AlertCircle, Check, RefreshCw, Search, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "@/components/ui/toast";
import { useAppStore } from "@/stores/appStore";
import { useSkillStore } from "@/stores/skillStore";
import { replaceSessionSkills } from "@/services/gerclaw/skills";
import { cn } from "@/lib/utils";

interface SkillSelectorProps {
  children?: React.ReactNode;
  className?: string;
  showLabel?: boolean;
}
const MAX_LOADED_SKILLS = 10;

export function SkillSelector({ children, className, showLabel = false }: SkillSelectorProps) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const currentSessionId = useAppStore((state) => state.currentSessionId);
  const loadedSkillIds = useAppStore((state) => state.loadedSkillIds);
  const setLoadedSkills = useAppStore((state) => state.setLoadedSkills);
  const skills = useSkillStore((state) => state.skills);
  const status = useSkillStore((state) => state.status);
  const error = useSkillStore((state) => state.error);
  const refresh = useSkillStore((state) => state.refresh);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    return skills.filter(
      (skill) =>
        skill.enabled &&
        (!normalized ||
          `${skill.name} ${skill.description} ${skill.category}`
            .toLocaleLowerCase("zh-CN")
            .includes(normalized))
    );
  }, [query, skills]);

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next && (status === "idle" || status === "error")) void refresh();
  };

  const handleToggle = async (skillId: string) => {
    const loaded = loadedSkillIds.includes(skillId);
    if (!loaded && loadedSkillIds.length >= MAX_LOADED_SKILLS) {
      toast.show(`每个对话最多加载 ${MAX_LOADED_SKILLS} 个技能`);
      return;
    }
    const next = loaded
      ? loadedSkillIds.filter((id) => id !== skillId)
      : [...loadedSkillIds, skillId];
    setBusy(skillId);
    try {
      setLoadedSkills(currentSessionId ? await replaceSessionSkills(currentSessionId, next) : next);
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "技能选择未保存");
    } finally {
      setBusy(null);
    }
  };

  return (
    <DropdownMenu open={open} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger
        render={
          children ? (
            (children as React.ReactElement)
          ) : (
            <Button
              variant="ghost"
              size="icon"
              className={cn("btn-icon", className)}
              aria-label="选择技能"
              aria-haspopup="menu"
              aria-expanded={open}
            />
          )
        }
      >
        <Workflow className="size-4" />
        {showLabel && <span>技能</span>}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-[min(24rem,calc(100vw-2rem))] p-0">
        <div className="border-b border-border p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <p className={cn("text-sm font-semibold", seniorMode && "text-lg")}>加载临床技能</p>
              <p className={cn("text-xs text-muted-foreground", seniorMode && "text-lg leading-8")}>AgentScope 将在本轮按需读取技能步骤</p>
            </div>
            <span className={cn("rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary", seniorMode && "text-lg")}>
              {loadedSkillIds.length}/{MAX_LOADED_SKILLS}
            </span>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索技能"
              className={cn("h-9 pl-8", seniorMode && "h-12 text-lg")}
              aria-label="搜索技能"
            />
          </div>
        </div>

        <ScrollArea className="h-72">
          {status === "loading" && skills.length === 0 ? (
            <div
              className={cn("flex h-32 flex-col items-center justify-center gap-1 text-sm text-muted-foreground", seniorMode && "text-lg")}
              role="status"
              aria-live="polite"
            >
              <Workflow className="size-4 text-primary" aria-hidden="true" />
              正在读取技能
            </div>
          ) : status === "error" && skills.length === 0 ? (
            <div
              className={cn("flex min-h-40 flex-col items-center justify-center gap-2 px-5 py-4 text-center", seniorMode && "text-lg leading-8")}
              role="alert"
            >
              <AlertCircle className="size-5 text-destructive" aria-hidden="true" />
              <p className="font-medium text-foreground">技能暂时无法读取</p>
              <p className={cn("text-xs text-muted-foreground", seniorMode && "text-lg leading-8")}>
                {error ?? "请检查网络后重新加载。"}
              </p>
              <Button
                type="button"
                variant="outline"
                size={seniorMode ? "default" : "sm"}
                className={cn(seniorMode && "min-h-12 px-3 text-base")}
                onClick={() => void refresh()}
              >
                <RefreshCw className="size-4" aria-hidden="true" />
                重新加载
              </Button>
            </div>
          ) : filtered.length === 0 ? (
            <div className={cn("px-5 py-10 text-center text-sm text-muted-foreground", seniorMode && "text-lg")}>
              没有匹配的可用技能
            </div>
          ) : (
            <ul className="p-1.5">
              {filtered.map((skill) => {
                const loaded = loadedSkillIds.includes(skill.skill_id);
                return (
                  <li key={skill.skill_id}>
                    <button
                      type="button"
                      onClick={() => void handleToggle(skill.skill_id)}
                      disabled={busy !== null}
                      className={cn(
                        "flex min-h-14 w-full items-start gap-3 rounded-lg px-2.5 py-2 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring",
                        seniorMode && "min-h-16 py-3"
                      )}
                      aria-pressed={loaded}
                      aria-label={
                        busy === skill.skill_id
                          ? `正在保存${skill.name}的选择`
                          : loaded
                            ? `从当前对话移除${skill.name}`
                            : `加载${skill.name}到当前对话`
                      }
                    >
                      <span className={cn("mt-0.5 flex size-5 shrink-0 items-center justify-center rounded border", loaded ? "border-primary bg-primary text-primary-foreground" : "border-border")}>
                        {busy === skill.skill_id ? <span className="text-xs font-semibold" aria-hidden="true">…</span> : loaded ? <Check className="size-3" /> : null}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className={cn("block truncate text-sm font-medium", seniorMode && "text-lg")}>
                          {skill.name}{busy === skill.skill_id ? "（正在保存）" : ""}
                        </span>
                        <span className={cn("mt-0.5 block line-clamp-2 text-xs leading-5 text-muted-foreground", seniorMode && "text-lg leading-8")}>
                          {skill.description}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </ScrollArea>
        <div className={cn("border-t border-border px-3 py-2 text-xs text-muted-foreground", seniorMode && "text-lg leading-8")}>
          技能只能声明已允许的检索工具，不能执行任意代码。
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
