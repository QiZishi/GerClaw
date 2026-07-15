"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Bot, FileUp, Plus, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "@/components/ui/toast";
import { SkillCard } from "@/components/skills/SkillCard";
import {
  SkillEditorDialog,
  type SkillEditorMode,
} from "@/components/skills/SkillCreateDialog";
import { useAppStore } from "@/stores/appStore";
import { useSkillStore } from "@/stores/skillStore";
import { replaceSessionSkills } from "@/services/gerclaw/skills";
import type { SkillDefinition, SkillInfo } from "@/services/gerclaw/schemas";
import { cn } from "@/lib/utils";

const MAX_LOADED_SKILLS = 10;

interface EditorState {
  mode: SkillEditorMode;
  definition?: SkillDefinition;
}

export function SkillManager() {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const currentSessionId = useAppStore((state) => state.currentSessionId);
  const loadedSkillIds = useAppStore((state) => state.loadedSkillIds);
  const setLoadedSkills = useAppStore((state) => state.setLoadedSkills);
  const skills = useSkillStore((state) => state.skills);
  const status = useSkillStore((state) => state.status);
  const error = useSkillStore((state) => state.error);
  const refresh = useSkillStore((state) => state.refresh);
  const load = useSkillStore((state) => state.load);
  const toggle = useSkillStore((state) => state.toggle);
  const remove = useSkillStore((state) => state.remove);
  const inspectUpload = useSkillStore((state) => state.inspectUpload);
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [busySkillId, setBusySkillId] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    if (!normalized) return skills;
    return skills.filter((skill) =>
      [skill.name, skill.description, skill.category, ...skill.tool_names].some((value) =>
        value.toLocaleLowerCase("zh-CN").includes(normalized)
      )
    );
  }, [query, skills]);

  const builtinSkills = filtered.filter((skill) => skill.source === "builtin");
  const customSkills = filtered.filter((skill) => skill.source === "custom");

  const updateSelection = async (next: string[]) => {
    if (currentSessionId) {
      setLoadedSkills(await replaceSessionSkills(currentSessionId, next));
    } else {
      setLoadedSkills(next);
    }
  };

  const handleLoadToggle = async (skill: SkillInfo) => {
    const loaded = loadedSkillIds.includes(skill.skill_id);
    if (!loaded && loadedSkillIds.length >= MAX_LOADED_SKILLS) {
      toast.show(`每个对话最多加载 ${MAX_LOADED_SKILLS} 个技能`);
      return;
    }
    const next = loaded
      ? loadedSkillIds.filter((id) => id !== skill.skill_id)
      : [...loadedSkillIds, skill.skill_id];
    setBusySkillId(skill.skill_id);
    try {
      await updateSelection(next);
      toast.show(loaded ? "已从当前对话移除" : "已加载到当前对话");
    } catch (selectionError) {
      toast.show(selectionError instanceof Error ? selectionError.message : "技能加载失败");
    } finally {
      setBusySkillId(null);
    }
  };

  const handleEnabledChange = async (skill: SkillInfo, enabled: boolean) => {
    setBusySkillId(skill.skill_id);
    try {
      await toggle(skill, enabled);
      if (!enabled && loadedSkillIds.includes(skill.skill_id)) {
        await updateSelection(loadedSkillIds.filter((id) => id !== skill.skill_id));
      }
      toast.show(enabled ? "技能已启用" : "技能已停用");
    } catch (toggleError) {
      toast.show(toggleError instanceof Error ? toggleError.message : "状态更新失败");
    } finally {
      setBusySkillId(null);
    }
  };

  const handleDelete = async (skill: SkillInfo) => {
    if (!window.confirm(`删除“${skill.name}”？此操作无法撤销。`)) return;
    setBusySkillId(skill.skill_id);
    try {
      if (loadedSkillIds.includes(skill.skill_id)) {
        await updateSelection(loadedSkillIds.filter((id) => id !== skill.skill_id));
      }
      await remove(skill);
      toast.show("自定义技能已删除");
    } catch (deleteError) {
      toast.show(deleteError instanceof Error ? deleteError.message : "删除失败");
    } finally {
      setBusySkillId(null);
    }
  };

  const handleUpload = async (file: File | undefined) => {
    if (!file) return;
    try {
      const definition = await inspectUpload(file);
      setEditor({ mode: "upload", definition });
      toast.show("技能包校验通过，请完整审阅后保存");
    } catch (uploadError) {
      toast.show(uploadError instanceof Error ? uploadError.message : "技能包导入失败");
    } finally {
      if (uploadRef.current) uploadRef.current.value = "";
    }
  };

  const handleOpenSkill = async (skill: SkillInfo, mode: "view" | "edit") => {
    setBusySkillId(skill.skill_id);
    try {
      setEditor({ mode, definition: await load(skill.skill_id) });
    } catch (loadError) {
      toast.show(loadError instanceof Error ? loadError.message : "技能内容读取失败");
    } finally {
      setBusySkillId(null);
    }
  };

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col bg-background" aria-label="技能工作台">
      <header className="border-b border-border bg-background/95 px-5 pb-4 pt-5 backdrop-blur md:px-8">
        <div className="mx-auto flex max-w-5xl flex-col gap-5">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="min-w-0">
              <div className={cn("mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground", seniorMode && "text-lg")}>
                <span className={cn("flex size-6 items-center justify-center rounded-md border border-primary/25 bg-primary/8 text-primary", seniorMode && "size-12")}>
                  <Bot className={cn("size-3.5", seniorMode && "size-6")} aria-hidden="true" />
                </span>
                AgentScope runtime
              </div>
              <h1 className={cn("text-2xl font-semibold tracking-tight", seniorMode && "text-3xl")}>
                临床技能工作台
              </h1>
              <p className={cn("mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground", seniorMode && "text-lg leading-8")}>
                选择经过策略校验的工作流，让当前对话按固定步骤检索证据、追问并整理结果。
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <input
                ref={uploadRef}
                type="file"
                accept=".md,.skill,.zip,text/markdown,application/zip"
                className="sr-only"
                onChange={(event) => void handleUpload(event.target.files?.[0])}
              />
              <Button variant="outline" onClick={() => uploadRef.current?.click()} className={cn(seniorMode && "h-12 px-4 text-lg")}>
                <FileUp className="size-4" aria-hidden="true" />
                导入技能包
              </Button>
              <Button onClick={() => setEditor({ mode: "create" })} className={cn(seniorMode && "h-12 px-4 text-lg")}>
                <Plus className="size-4" aria-hidden="true" />
                新建技能
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-3 rounded-xl border border-border bg-muted/25 p-3 sm:flex-row sm:items-center">
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索名称、用途或可用工具"
                className={cn("h-10 bg-background pl-9", seniorMode && "h-12 text-lg")}
                aria-label="搜索技能"
              />
            </div>
            <div className={cn("flex items-center gap-4 px-1 text-xs text-muted-foreground", seniorMode && "text-lg")}>
              <span><strong className="font-semibold text-foreground">{skills.length}</strong> 个可用</span>
              <span><strong className="font-semibold text-primary">{loadedSkillIds.length}</strong> 个已加载</span>
            </div>
          </div>
        </div>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto max-w-5xl space-y-8 px-5 py-6 md:px-8">
          {status === "loading" && skills.length === 0 && <SkillSkeleton />}
          {status === "error" && skills.length === 0 && (
            <div className="flex min-h-52 flex-col items-center justify-center rounded-xl border border-dashed border-destructive/40 bg-destructive/5 px-6 text-center">
              <AlertCircle className="mb-3 size-6 text-destructive" aria-hidden="true" />
              <p className={cn("font-medium", seniorMode && "text-xl")}>技能列表未加载</p>
              <p className={cn("mt-1 text-sm text-muted-foreground", seniorMode && "text-lg leading-8")}>{error}</p>
              <Button variant="outline" className={cn("mt-4", seniorMode && "h-12 px-4 text-lg")} onClick={() => void refresh()}>
                <RefreshCw className="size-4" aria-hidden="true" />
                重新加载
              </Button>
            </div>
          )}
          {status !== "loading" && filtered.length === 0 && status !== "error" && (
            <div className="rounded-xl border border-dashed border-border px-6 py-14 text-center">
              <p className={cn("font-medium", seniorMode && "text-xl")}>没有匹配的技能</p>
              <p className={cn("mt-1 text-sm text-muted-foreground", seniorMode && "text-lg leading-8")}>换一个关键词，或创建新的临床工作流。</p>
            </div>
          )}
          {builtinSkills.length > 0 && (
            <SkillSection title="系统技能" description="随系统发布，只读并经过统一安全策略校验。" seniorMode={seniorMode}>
              {builtinSkills.map((skill) => (
                <SkillCard
                  key={skill.skill_id}
                  skill={skill}
                  loaded={loadedSkillIds.includes(skill.skill_id)}
                  busy={busySkillId === skill.skill_id}
                  seniorMode={seniorMode}
                  onLoadToggle={() => void handleLoadToggle(skill)}
                  onView={() => void handleOpenSkill(skill, "view")}
                />
              ))}
            </SkillSection>
          )}
          {customSkills.length > 0 && (
            <SkillSection title="我的技能" description="由您上传或通过真实模型生成，保存前可完整审阅。" seniorMode={seniorMode}>
              {customSkills.map((skill) => (
                <SkillCard
                  key={skill.skill_id}
                  skill={skill}
                  loaded={loadedSkillIds.includes(skill.skill_id)}
                  busy={busySkillId === skill.skill_id}
                  seniorMode={seniorMode}
                  onLoadToggle={() => void handleLoadToggle(skill)}
                  onView={() => void handleOpenSkill(skill, "view")}
                  onEdit={() => void handleOpenSkill(skill, "edit")}
                  onEnabledChange={(enabled) => void handleEnabledChange(skill, enabled)}
                  onDelete={() => void handleDelete(skill)}
                />
              ))}
            </SkillSection>
          )}
        </div>
      </ScrollArea>
      {editor && (
        <SkillEditorDialog
          key={`${editor.mode}:${editor.definition?.skill_id ?? "new"}:${editor.definition?.revision ?? 0}`}
          mode={editor.mode}
          definition={editor.definition}
          onOpenChange={(open) => {
            if (!open) setEditor(null);
          }}
          seniorMode={seniorMode}
        />
      )}
    </main>
  );
}
function SkillSection({ title, description, children, seniorMode }: { title: string; description: string; children: React.ReactNode; seniorMode: boolean }) {
  return (
    <section aria-labelledby={`skill-section-${title}`}>
      <div className="mb-3 flex items-end justify-between gap-4 border-b border-border pb-3">
        <div>
          <h2 id={`skill-section-${title}`} className={cn("font-semibold", seniorMode && "text-xl")}>{title}</h2>
          <p className={cn("mt-0.5 text-xs text-muted-foreground", seniorMode && "text-lg leading-8")}>{description}</p>
        </div>
      </div>
      <ul className="grid gap-3 lg:grid-cols-2">{children}</ul>
    </section>
  );
}

function SkillSkeleton() {
  return (
    <div
      className="flex min-h-52 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-6 text-center"
      role="status"
      aria-live="polite"
    >
      <Bot className="mb-3 size-6 text-primary" aria-hidden="true" />
      <p className="font-medium">正在读取可用技能</p>
      <p className="mt-1 text-sm text-muted-foreground">
        请稍候。技能列表准备完成后会显示在这里。
      </p>
    </div>
  );
}
