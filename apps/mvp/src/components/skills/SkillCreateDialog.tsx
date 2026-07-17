"use client";

import { useState } from "react";
import { Bot, ShieldCheck } from "lucide-react";
import { MarkdownEditor } from "@/components/editor/MarkdownEditor";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { SkillDefinition, SkillDraft } from "@/services/gerclaw/schemas";
import { useSkillStore } from "@/stores/skillStore";

const TEMPLATE = `---
id: my-safe-workflow
name: 我的安全工作流
description: 描述这个工作流帮助用户完成什么
version: 1.0.0
category: general
parameters: {}
tools:
  - search_knowledge
---
# 工作流

先核对用户目标，再检索本地证据，标注来源并生成供人工复核的草稿。
禁止确定性诊断；发现高风险症状时提示立即就医。
`;

const DRAFT_CHECK_LABELS: Record<SkillDraft["quality_report"]["missing_checks"][number], string> = {
  input_check: "先核对输入信息",
  local_evidence: "说明本地证据或引用要求",
  red_flag: "说明红旗或紧急就医处理",
  medical_disclaimer: "加入医疗免责声明",
};

export type SkillEditorMode = "create" | "upload" | "edit" | "view";

interface SkillEditorDialogProps {
  mode: SkillEditorMode;
  definition?: SkillDefinition;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
}

const MODE_CONTENT: Record<
  SkillEditorMode,
  { title: string; description: string; saveLabel?: string }
> = {
  create: {
    title: "创建临床技能",
    description: "AI 只生成待审阅草稿。保存前，后端会再次校验工具权限、参数边界和医疗安全策略。",
    saveLabel: "审阅完成并保存",
  },
  upload: {
    title: "审阅导入的技能",
    description: "技能包已通过结构校验，但尚未注册。请完整检查并按需修改 SKILL.md，确认后再保存。",
    saveLabel: "确认并注册技能",
  },
  edit: {
    title: "编辑临床技能",
    description: "修改会创建新的修订版本，并使用当前修订号防止覆盖其他窗口中的更新。",
    saveLabel: "保存新修订",
  },
  view: {
    title: "查看临床技能",
    description: "可在渲染预览与完整 SKILL.md 源码间切换。系统内置技能为只读。",
  },
};

export function SkillEditorDialog({
  mode,
  definition,
  onOpenChange,
  seniorMode,
}: SkillEditorDialogProps) {
  const create = useSkillStore((state) => state.create);
  const update = useSkillStore((state) => state.update);
  const generateDraft = useSkillStore((state) => state.generateDraft);
  const evolveDraft = useSkillStore((state) => state.evolveDraft);
  const [description, setDescription] = useState("");
  const [changeRequest, setChangeRequest] = useState("");
  const [markdown, setMarkdown] = useState(definition?.source_markdown ?? TEMPLATE);
  const [origin, setOrigin] = useState<"text" | "upload" | "generated">(
    mode === "upload" ? "upload" : "text"
  );
  const [busy, setBusy] = useState<"generate" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftQuality, setDraftQuality] = useState<SkillDraft["quality_report"] | null>(null);
  const copy = MODE_CONTENT[mode];
  const readOnly = mode === "view";

  const handleOpenChange = (next: boolean) => {
    if (!busy) onOpenChange(next);
  };

  const handleGenerate = async () => {
    if (description.trim().length < 10) {
      setError("请至少用 10 个字说明技能目标和适用场景。");
      return;
    }
    setBusy("generate");
    setError(null);
    try {
      const draft = await generateDraft(description.trim());
      setMarkdown(draft.definition.source_markdown);
      setDraftQuality(draft.quality_report);
      setOrigin("generated");
      toast.show("真实模型已生成草稿，请根据审阅提示完整检查后保存");
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "草稿生成失败");
    } finally {
      setBusy(null);
    }
  };

  const handleSave = async () => {
    if (!markdown.trim()) return;
    setBusy("save");
    setError(null);
    try {
      if (mode === "edit" && definition) {
        await update(definition, markdown);
        toast.show("技能新修订已保存");
      } else {
        await create(markdown, origin);
        toast.show("技能已通过校验并保存");
      }
      onOpenChange(false);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "技能保存失败");
    } finally {
      setBusy(null);
    }
  };

  const handleEvolve = async () => {
    if (!definition || changeRequest.trim().length < 10) {
      setError("请至少用 10 个字说明希望如何优化这个技能。");
      return;
    }
    setBusy("generate");
    setError(null);
    try {
      const draft = await evolveDraft(definition, changeRequest.trim());
      setMarkdown(draft.definition.source_markdown);
      setDraftQuality(draft.quality_report);
      setOrigin("generated");
      toast.show("已生成新的待审阅修订；确认无误后再保存");
    } catch (evolutionError) {
      setError(evolutionError instanceof Error ? evolutionError.message : "修订草稿生成失败");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        className={cn(
          "flex max-h-[92vh] flex-col overflow-hidden sm:max-w-3xl",
          seniorMode && "sm:max-w-4xl"
        )}
      >
        <DialogHeader>
          <div className={cn(
            "mb-2 flex size-10 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary",
            seniorMode && "size-12"
          )}>
            {readOnly ? <ShieldCheck className="size-5" aria-hidden="true" /> : <Bot className="size-5" aria-hidden="true" />}
          </div>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>{copy.title}</DialogTitle>
          <DialogDescription className={cn("leading-6", seniorMode && "text-lg leading-8")}>
            {copy.description}
          </DialogDescription>
        </DialogHeader>

        {mode === "create" && (
          <section className="space-y-3 rounded-xl border border-border bg-muted/20 p-4" aria-labelledby="skill-ai-draft-title">
            <div>
              <Label id="skill-ai-draft-title" htmlFor="skill-description" className={cn(seniorMode && "text-lg")}>
                让真实模型生成起始草稿（可选）
              </Label>
              <p className={cn("mt-1 text-xs text-muted-foreground", seniorMode && "text-lg leading-8")}>
                生成后仍可逐字修改；模型草稿不会自动注册。
              </p>
            </div>
            <textarea
              id="skill-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={2_000}
              placeholder="例如：为老年高血压患者准备复诊问题清单，先核对近期血压和用药，再检索本地指南并标注来源。"
              className={cn(
                "min-h-24 w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm leading-6 outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40",
                seniorMode && "min-h-36 text-lg leading-8"
              )}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className={cn("text-xs text-muted-foreground", seniorMode && "text-lg")}>{description.length}/2000</span>
              <Button
                variant="outline"
                onClick={() => void handleGenerate()}
                disabled={busy !== null}
                className={cn(seniorMode && "h-12 px-4 text-lg")}
              >
                {busy === "generate" ? <span className="text-base leading-none" aria-hidden="true">…</span> : <Bot className="size-5" />}
                {busy === "generate" ? "正在生成草稿" : "生成可审阅草稿"}
              </Button>
            </div>
          </section>
        )}

        {draftQuality && (
          <section
            className={cn(
              "rounded-xl border px-4 py-3",
              draftQuality.missing_checks.length
                ? "border-amber-500/35 bg-amber-500/10"
                : "border-emerald-600/30 bg-emerald-600/10"
            )}
            aria-live="polite"
            aria-label="模型草稿审阅提示"
          >
            <p className={cn("font-medium", seniorMode && "text-lg")}>
              {draftQuality.missing_checks.length
                ? "保存前请补充或核实以下内容"
                : "草稿已覆盖基础审阅提示，仍需人工逐字审阅"}
            </p>
            {draftQuality.missing_checks.length > 0 && (
              <ul className={cn("mt-2 list-disc space-y-1 pl-5 text-sm leading-6", seniorMode && "text-lg leading-8")}>
                {draftQuality.missing_checks.map((check) => (
                  <li key={check}>{DRAFT_CHECK_LABELS[check]}</li>
                ))}
              </ul>
            )}
            <p className={cn("mt-2 text-xs leading-5 text-muted-foreground", seniorMode && "text-base leading-7")}>
              这只是结构化审阅提示，不代表医学正确性、医生批准或自动发布。
            </p>
          </section>
        )}

        {mode === "edit" && definition && (
          <section className="space-y-3 rounded-xl border border-border bg-muted/20 p-4" aria-labelledby="skill-evolution-title">
            <div>
              <Label id="skill-evolution-title" htmlFor="skill-change-request" className={cn(seniorMode && "text-lg")}>
                生成优化修订草稿（可选）
              </Label>
              <p className={cn("mt-1 text-xs text-muted-foreground", seniorMode && "text-lg leading-8")}>
                保持技能编号不变，只生成更高版本的待审阅草稿；不会自动保存或启用。
              </p>
            </div>
            <textarea
              id="skill-change-request"
              value={changeRequest}
              onChange={(event) => setChangeRequest(event.target.value)}
              maxLength={2_000}
              placeholder="例如：增加对用户提供信息是否完整的核对步骤，并让输出先列出待向医生确认的问题。"
              className={cn(
                "min-h-24 w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm leading-6 outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40",
                seniorMode && "min-h-36 text-lg leading-8"
              )}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className={cn("text-xs text-muted-foreground", seniorMode && "text-lg")}>{changeRequest.length}/2000</span>
              <Button
                variant="outline"
                onClick={() => void handleEvolve()}
                disabled={busy !== null}
                className={cn(seniorMode && "h-12 px-4 text-lg")}
              >
                {busy === "generate" ? <span className="text-base leading-none" aria-hidden="true">…</span> : <Bot className="size-5" />}
                {busy === "generate" ? "正在生成修订" : "生成待审阅修订"}
              </Button>
            </div>
          </section>
        )}

        <section className="flex min-h-72 flex-1 flex-col overflow-hidden rounded-xl border border-border" aria-labelledby="skill-markdown-title">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2">
            <Label id="skill-markdown-title" className={cn(seniorMode && "text-lg")}>完整 SKILL.md</Label>
            <span className={cn("inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400", seniorMode && "text-lg")}>
              <ShieldCheck className="size-4" aria-hidden="true" />
              {readOnly ? "只读查看" : "保存时重新校验"}
            </span>
          </div>
          <MarkdownEditor
            value={markdown}
            onChange={(value) => {
              setMarkdown(value);
              setDraftQuality(null);
            }}
            readOnly={readOnly}
            seniorMode={seniorMode}
            defaultMode={readOnly ? "preview" : "source"}
            className="min-h-72"
          />
        </section>

        {error && (
          <div role="alert" className={cn("rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive", seniorMode && "text-lg leading-8")}>
            {error}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={busy !== null}
            className={cn(seniorMode && "h-12 px-4 text-lg")}
          >
            {readOnly ? "关闭" : "取消"}
          </Button>
          {!readOnly && (
            <Button
              onClick={() => void handleSave()}
              disabled={busy !== null || !markdown.trim()}
              className={cn(seniorMode && "h-12 px-4 text-lg")}
            >
              {busy === "save" && <span className="text-base leading-none" aria-hidden="true">…</span>}
              {busy === "save" ? "正在保存" : copy.saveLabel}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
