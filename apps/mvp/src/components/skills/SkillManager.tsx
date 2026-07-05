"use client";

import { useMemo, useState } from "react";
import {
  Plus,
  Search,
  Sparkles,
  Trash2,
  Zap,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { useAppStore } from "@/stores/appStore";
import { mockSkills, type MockSkill } from "@/data/mock/skills";
import { generateId } from "@/lib/format";
import { cn } from "@/lib/utils";

type SkillCategory = MockSkill["category"];

const CATEGORIES: SkillCategory[] = ["通用", "专科", "自定义"];

const CATEGORY_DESC: Record<SkillCategory, string> = {
  通用: "通用辅助技能，覆盖用药提醒、健康宣教等",
  专科: "老年专科疾病管理技能，对应循证指南",
  自定义: "用户自建技能（mock 阶段仅保存在内存）",
};

interface CreateSkillInput {
  name: string;
  description: string;
  content: string;
}

/**
 * §技能管理 右侧动态面板
 * - 顶部搜索 + "创建自定义技能" 按钮
 * - 按 category 分组渲染技能列表（通用/专科/自定义）
 * - 每条技能卡片：图标 + 名称 + 描述 + 标签 + Switch 启用开关 + 加载按钮
 * - 创建自定义技能：弹 Dialog 输入名称/描述/内容（mock 仅写入本地 state）
 *
 * 严格 mock：所有操作仅修改内存（不调用 localStorage / API）
 */
export function SkillManager() {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const loadedSkillIds = useAppStore((s) => s.loadedSkillIds);
  const addLoadedSkill = useAppStore((s) => s.addLoadedSkill);
  const removeLoadedSkill = useAppStore((s) => s.removeLoadedSkill);

  const [query, setQuery] = useState("");
  const [skills, setSkills] = useState<MockSkill[]>(mockSkills);
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState<CreateSkillInput>({
    name: "",
    description: "",
    content: "",
  });
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2000);
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.tags.some((t) => t.toLowerCase().includes(q))
    );
  }, [skills, query]);

  const grouped = useMemo(() => {
    const map: Record<SkillCategory, MockSkill[]> = {
      通用: [],
      专科: [],
      自定义: [],
    };
    filtered.forEach((s) => {
      map[s.category].push(s);
    });
    return map;
  }, [filtered]);

  const handleToggleEnabled = (id: string, enabled: boolean) => {
    setSkills((prev) =>
      prev.map((s) => (s.id === id ? { ...s, enabled } : s))
    );
    if (!enabled && loadedSkillIds.includes(id)) {
      removeLoadedSkill(id);
    }
    showToast(enabled ? "技能已启用" : "技能已禁用并从输入框移除");
  };

  const handleLoadToggle = (skill: MockSkill) => {
    if (!skill.enabled) return;
    if (loadedSkillIds.includes(skill.id)) {
      removeLoadedSkill(skill.id);
    } else {
      addLoadedSkill(skill.id);
      showToast(`已加载技能：${skill.name}`);
    }
  };

  const handleCreate = () => {
    const name = draft.name.trim();
    if (!name) {
      showToast("请输入技能名称");
      return;
    }
    if (skills.some((s) => s.name === name)) {
      showToast("技能名称已存在");
      return;
    }
    const newSkill: MockSkill = {
      id: `skill_custom_${generateId()}`,
      name,
      description: draft.description.trim() || "用户自定义技能",
      category: "自定义",
      enabled: true,
      source: "custom",
      tags: ["自定义"],
    };
    setSkills((prev) => [...prev, newSkill]);
    setDraft({ name: "", description: "", content: "" });
    setCreateOpen(false);
    showToast("自定义技能创建成功（仅保存在内存）");
  };

  const handleDeleteCustom = (id: string) => {
    setSkills((prev) => prev.filter((s) => s.id !== id));
    if (loadedSkillIds.includes(id)) {
      removeLoadedSkill(id);
    }
    showToast("自定义技能已删除");
  };

  return (
    <div className="flex flex-col h-full">
      {/* 顶部操作区 */}
      <div className="px-3 py-2 border-b border-border space-y-2">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <Input
              type="text"
              placeholder="搜索技能"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="h-7 pl-7 text-xs"
              aria-label="搜索技能"
            />
          </div>
          <Button
            variant="default"
            size="sm"
            className="gap-1 shrink-0"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="size-3.5" />
            <span>新建</span>
          </Button>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>共 {skills.length} 个技能</span>
          <span>已加载 {loadedSkillIds.length}</span>
        </div>
      </div>

      {/* 技能列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-3 space-y-4">
          {CATEGORIES.map((cat) => {
            const list = grouped[cat];
            if (list.length === 0) return null;
            return (
              <section key={cat} aria-labelledby={`cat-${cat}`}>
                <header className="mb-2">
                  <h3
                    className={cn(
                      "text-xs font-semibold text-muted-foreground uppercase tracking-wide",
                      seniorMode && "text-sm"
                    )}
                    id={`cat-${cat}`}
                  >
                    {cat}技能
                  </h3>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {CATEGORY_DESC[cat]}
                  </p>
                </header>
                <ul className="space-y-2">
                  {list.map((skill) => (
                    <SkillCard
                      key={skill.id}
                      skill={skill}
                      loaded={loadedSkillIds.includes(skill.id)}
                      onToggleLoad={() => handleLoadToggle(skill)}
                      onToggleEnabled={(en) =>
                        handleToggleEnabled(skill.id, en)
                      }
                      onDelete={
                        skill.source === "custom"
                          ? () => handleDeleteCustom(skill.id)
                          : undefined
                      }
                    />
                  ))}
                </ul>
              </section>
            );
          })}
          {filtered.length === 0 && (
            <div className="text-center text-xs text-muted-foreground py-8">
              未找到匹配的技能
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Toast */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 rounded-md border border-border bg-popover px-3 py-1.5 text-xs text-popover-foreground shadow-md whitespace-nowrap"
        >
          {toast}
        </div>
      )}

      {/* 创建自定义技能 Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>创建自定义技能</DialogTitle>
            <DialogDescription>
              自定义技能将作为指令注入对话，仅保存在内存中（刷新后丢失）。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="skill-name">技能名称</Label>
              <Input
                id="skill-name"
                value={draft.name}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, name: e.target.value }))
                }
                placeholder="例如：糖尿病足护理"
                maxLength={30}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="skill-desc">技能描述</Label>
              <Input
                id="skill-desc"
                value={draft.description}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, description: e.target.value }))
                }
                placeholder="一句话描述技能用途"
                maxLength={80}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="skill-content">技能内容（Markdown）</Label>
              <textarea
                id="skill-content"
                value={draft.content}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, content: e.target.value }))
                }
                placeholder={"# 角色设定\n你是一名…\n\n# 任务流程\n1. …"}
                rows={6}
                className="font-mono text-xs w-full rounded-lg border border-input bg-transparent px-2.5 py-1 outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                maxLength={2000}
              />
              <p className="text-[10px] text-muted-foreground text-right">
                {draft.content.length}/2000
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button variant="default" onClick={handleCreate}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface SkillCardProps {
  skill: MockSkill;
  loaded: boolean;
  onToggleLoad: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  onDelete?: () => void;
}

function SkillCard({
  skill,
  loaded,
  onToggleLoad,
  onToggleEnabled,
  onDelete,
}: SkillCardProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const Icon = skill.source === "custom" ? Sparkles : Zap;

  return (
    <li
      className={cn(
        "rounded-lg border border-border bg-card p-2.5 transition-colors",
        loaded && "border-primary/40 bg-primary/5",
        !skill.enabled && "opacity-60"
      )}
    >
      <div className="flex items-start gap-2">
        <div
          className={cn(
            "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md",
            skill.source === "custom"
              ? "bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300"
              : "bg-primary/10 text-primary"
          )}
        >
          <Icon className="size-3.5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span
              className={cn(
                "text-sm font-medium truncate",
                seniorMode && "text-base"
              )}
            >
              {skill.name}
            </span>
            {loaded && (
              <Badge variant="secondary" className="text-[10px] py-0">
                已加载
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
            {skill.description}
          </p>
          {skill.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {skill.tags.map((t) => (
                <span
                  key={t}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
        <Switch
          checked={skill.enabled}
          onCheckedChange={onToggleEnabled}
          aria-label={`启用或禁用技能 ${skill.name}`}
        />
      </div>
      <Separator className="my-2" />
      <div className="flex items-center justify-between">
        <Button
          variant={loaded ? "outline" : "default"}
          size="sm"
          className="gap-1 h-7"
          onClick={onToggleLoad}
          disabled={!skill.enabled}
        >
          <Zap className="size-3" />
          {loaded ? "卸载" : "加载"}
        </Button>
        {onDelete && (
          <Button
            variant="ghost"
            size="sm"
            className="gap-1 h-7 text-destructive hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="size-3" />
            删除
          </Button>
        )}
      </div>
    </li>
  );
}
