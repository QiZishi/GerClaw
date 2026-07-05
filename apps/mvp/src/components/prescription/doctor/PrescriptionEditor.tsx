"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Plus,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Disclaimer } from "@/components/prescription/Disclaimer";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type {
  PrescriptionItem,
  PrescriptionReport,
  PrescriptionSection,
} from "@/types";

interface PrescriptionEditorProps {
  report: PrescriptionReport;
  onChange?: (report: PrescriptionReport) => void;
  className?: string;
}

/**
 * §6 处方编辑器（医生端）
 * 可编辑五大处方的 summary 与每个 item 的 detail/dosage/frequency
 * 仅医生端可用，保存后调用 onChange 上抛新报告
 */
export function PrescriptionEditor({
  report,
  onChange,
  className,
}: PrescriptionEditorProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    drug: true,
    exercise: false,
    nutrition: false,
    psychology: false,
    rehabilitation: false,
  });

  const updateSection = (type: string, summary: string) => {
    onChange?.({
      ...report,
      sections: report.sections.map((s) =>
        s.type === type ? { ...s, summary } : s
      ),
    });
  };

  const updateItem = (
    sectionType: string,
    itemIndex: number,
    field: keyof PrescriptionItem,
    value: string
  ) => {
    onChange?.({
      ...report,
      sections: report.sections.map((s) => {
        if (s.type !== sectionType) return s;
        const items = s.items.map((it, idx) =>
          idx === itemIndex ? { ...it, [field]: value } : it
        );
        return { ...s, items };
      }),
    });
  };

  const removeItem = (sectionType: string, itemIndex: number) => {
    onChange?.({
      ...report,
      sections: report.sections.map((s) => {
        if (s.type !== sectionType) return s;
        return { ...s, items: s.items.filter((_, idx) => idx !== itemIndex) };
      }),
    });
  };

  const addItem = (sectionType: string) => {
    const newItem: PrescriptionItem = {
      name: "新建议",
      detail: "请填写具体内容",
    };
    onChange?.({
      ...report,
      sections: report.sections.map((s) => {
        if (s.type !== sectionType) return s;
        return { ...s, items: [...s.items, newItem] };
      }),
    });
  };

  return (
    <div className={cn("flex flex-col h-full", className)}>
      <header className="px-3 py-2 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "font-medium",
              seniorMode ? "text-base" : "text-sm"
            )}
          >
            处方编辑器
          </span>
          <Badge variant="secondary" className="text-[10px]">
            编辑模式
          </Badge>
        </div>
        <span className="text-xs text-muted-foreground">
          {report.sections.reduce((acc, s) => acc + s.items.length, 0)} 项建议
        </span>
      </header>

      <ScrollArea className="flex-1 min-h-0">
        <div className="p-3 space-y-3">
          {report.sections.map((section) => (
            <SectionEditor
              key={section.type}
              section={section}
              expanded={!!expanded[section.type]}
              seniorMode={seniorMode}
              onToggle={() =>
                setExpanded((prev) => ({
                  ...prev,
                  [section.type]: !prev[section.type],
                }))
              }
              onUpdateSummary={(v) => updateSection(section.type, v)}
              onUpdateItem={(idx, field, v) =>
                updateItem(section.type, idx, field, v)
              }
              onRemoveItem={(idx) => removeItem(section.type, idx)}
              onAddItem={() => addItem(section.type)}
            />
          ))}
          <Disclaimer />
        </div>
      </ScrollArea>
    </div>
  );
}

interface SectionEditorProps {
  section: PrescriptionSection;
  expanded: boolean;
  seniorMode: boolean;
  onToggle: () => void;
  onUpdateSummary: (value: string) => void;
  onUpdateItem: (
    index: number,
    field: keyof PrescriptionItem,
    value: string
  ) => void;
  onRemoveItem: (index: number) => void;
  onAddItem: () => void;
}

function SectionEditor({
  section,
  expanded,
  seniorMode,
  onToggle,
  onUpdateSummary,
  onUpdateItem,
  onRemoveItem,
  onAddItem,
}: SectionEditorProps) {
  return (
    <section className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 hover:bg-muted/50 transition-colors"
        aria-expanded={expanded}
      >
        <span
          className={cn(
            "font-medium",
            seniorMode ? "text-base" : "text-sm"
          )}
        >
          {section.title}
        </span>
        <span className="flex items-center gap-2">
          <Badge variant="outline" className="text-[10px]">
            {section.items.length} 项
          </Badge>
          {expanded ? (
            <ChevronUp className="size-3.5 text-muted-foreground" />
          ) : (
            <ChevronDown className="size-3.5 text-muted-foreground" />
          )}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border p-3 space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">小节摘要</label>
            <Input
              value={section.summary}
              onChange={(e) => onUpdateSummary(e.target.value)}
              className="text-xs h-7"
            />
          </div>
          <Separator />
          <div className="space-y-3">
            {section.items.map((item, idx) => (
              <ItemEditor
                key={`${section.type}-${idx}`}
                item={item}
                index={idx}
                onUpdate={(field, v) => onUpdateItem(idx, field, v)}
                onRemove={() => onRemoveItem(idx)}
              />
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-1"
            onClick={onAddItem}
          >
            <Plus className="size-3.5" />
            添加建议
          </Button>
        </div>
      )}
    </section>
  );
}

interface ItemEditorProps {
  item: PrescriptionItem;
  index: number;
  onUpdate: (field: keyof PrescriptionItem, value: string) => void;
  onRemove: () => void;
}

function ItemEditor({ item, index, onUpdate, onRemove }: ItemEditorProps) {
  return (
    <div className="rounded-md border border-border/60 p-2 space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-muted-foreground shrink-0">
          #{index + 1}
        </span>
        <Input
          value={item.name}
          onChange={(e) => onUpdate("name", e.target.value)}
          className="text-xs h-7 flex-1 font-medium"
          aria-label="建议名称"
        />
        <Button
          variant="ghost"
          size="icon-sm"
          className="btn-icon text-destructive hover:text-destructive shrink-0"
          onClick={onRemove}
          aria-label="删除建议"
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      <div className="space-y-1">
        <label className="text-[11px] text-muted-foreground">说明</label>
        <Input
          value={item.detail}
          onChange={(e) => onUpdate("detail", e.target.value)}
          className="text-xs h-7"
        />
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        <div className="space-y-1">
          <label className="text-[11px] text-muted-foreground">剂量</label>
          <Input
            value={item.dosage ?? ""}
            onChange={(e) => onUpdate("dosage", e.target.value)}
            className="text-xs h-7"
            placeholder="—"
          />
        </div>
        <div className="space-y-1">
          <label className="text-[11px] text-muted-foreground">频次</label>
          <Input
            value={item.frequency ?? ""}
            onChange={(e) => onUpdate("frequency", e.target.value)}
            className="text-xs h-7"
            placeholder="—"
          />
        </div>
        <div className="space-y-1">
          <label className="text-[11px] text-muted-foreground">疗程</label>
          <Input
            value={item.duration ?? ""}
            onChange={(e) => onUpdate("duration", e.target.value)}
            className="text-xs h-7"
            placeholder="—"
          />
        </div>
      </div>
    </div>
  );
}
