"use client";

import { useMemo, useState } from "react";
import { Check, Search, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";
import { skills } from "@/data/skills";
import { cn } from "@/lib/utils";

interface SkillSelectorProps {
  /** 子元素作为触发器（默认渲染 Zap 图标按钮） */
  children?: React.ReactNode;
  className?: string;
}

/**
 * §3.4 输入框 ⚡ 按钮弹出技能快速选择器
 * 用 DropdownMenu 替代 Popover（项目未装 Popover）
 * 搜索 + 技能网格，点击切换加载/卸载状态
 * Mock 阶段：仅修改 appStore.loadedSkillIds，不调用真实接口
 */
export function SkillSelector({ children, className }: SkillSelectorProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const loadedSkillIds = useAppStore((s) => s.loadedSkillIds);
  const addLoadedSkill = useAppStore((s) => s.addLoadedSkill);
  const removeLoadedSkill = useAppStore((s) => s.removeLoadedSkill);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.tags.some((t) => t.toLowerCase().includes(q))
    );
  }, [query]);

  const toggle = (id: string) => {
    if (loadedSkillIds.includes(id)) {
      removeLoadedSkill(id);
    } else {
      addLoadedSkill(id);
    }
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        render={
          children ? (
            (children as React.ReactElement)
          ) : (
            <Button
              variant="ghost"
              size="icon"
              className={cn("btn-icon", className)}
              aria-label="技能"
              aria-haspopup="menu"
              aria-expanded={open}
            />
          )
        }
      >
        <Zap className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="top"
        className="w-80 p-0"
      >
        <div className="p-2 border-b border-border">
          <div className="flex items-center gap-2 mb-1.5">
            <Zap className="size-3.5 text-primary" />
            <span className="text-sm font-medium">技能快速选择</span>
          </div>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <Input
              type="text"
              placeholder="搜索技能名称/标签"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="h-7 pl-7 text-xs"
              aria-label="搜索技能"
            />
          </div>
        </div>

        <ScrollArea className="h-64">
          <ul className="py-1">
            {filtered.length === 0 && (
              <li className="px-3 py-4 text-center text-xs text-muted-foreground">
                未找到匹配的技能
              </li>
            )}
            {filtered.map((skill) => {
              const loaded = loadedSkillIds.includes(skill.id);
              const disabled = !skill.enabled;
              return (
                <li key={skill.id}>
                  <button
                    type="button"
                    onClick={() => toggle(skill.id)}
                    disabled={disabled}
                    className={cn(
                      "flex w-full items-start gap-2 px-3 py-2 text-left transition-colors",
                      "hover:bg-muted focus:bg-muted focus:outline-none",
                      disabled && "opacity-50 cursor-not-allowed hover:bg-transparent",
                      seniorMode && "py-2.5"
                    )}
                    aria-pressed={loaded}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border",
                        loaded
                          ? "bg-primary border-primary text-primary-foreground"
                          : "border-border"
                      )}
                    >
                      {loaded && <Check className="size-3" />}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="flex items-center gap-1.5">
                        <span
                          className={cn(
                            "text-sm font-medium truncate",
                            seniorMode && "text-base"
                          )}
                        >
                          {skill.name}
                        </span>
                        <span
                          className={cn(
                            "text-[10px] px-1 py-0.5 rounded shrink-0",
                            skill.source === "custom"
                              ? "bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300"
                              : "bg-muted text-muted-foreground"
                          )}
                        >
                          {skill.category}
                        </span>
                      </span>
                      <span className="block text-xs text-muted-foreground mt-0.5 line-clamp-2">
                        {skill.description}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </ScrollArea>

        <Separator />
        <div className="flex items-center justify-between px-3 py-2">
          <span className="text-xs text-muted-foreground">
            已加载 {loadedSkillIds.length} / {skills.length}
          </span>
          <Button
            variant="link"
            size="sm"
            className="h-6 px-1 text-xs"
            onClick={() => setOpen(false)}
          >
            完成
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
