"use client";

import { useState } from "react";
import { Loader2, Pill, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { DrugItem } from "@/types";

interface DrugInputProps {
  /** 审查回调，传入已添加的药物列表 */
  onReview?: (drugs: DrugItem[]) => void;
  /** 初始药物列表 */
  initialDrugs?: DrugItem[];
}

/**
 * §4.1 用药审查 — 药物输入界面
 * 可添加多个药物 + 删除 + 提交审查（mock 1s 延迟）
 */
export function DrugInput({ onReview, initialDrugs }: DrugInputProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [drugs, setDrugs] = useState<DrugItem[]>(initialDrugs ?? []);
  const [name, setName] = useState("");
  const [dosage, setDosage] = useState("");
  const [frequency, setFrequency] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const handleAdd = () => {
    if (!name.trim()) return;
    const drug: DrugItem = {
      id: `drug_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      name: name.trim(),
      dosage: dosage.trim() || undefined,
      frequency: frequency.trim() || undefined,
      route: "口服",
    };
    setDrugs((d) => [...d, drug]);
    setName("");
    setDosage("");
    setFrequency("");
  };

  const handleRemove = (id: string) => {
    setDrugs((d) => d.filter((x) => x.id !== id));
  };

  const handleReview = () => {
    if (drugs.length === 0) return;
    setReviewing(true);
    setTimeout(() => {
      setReviewing(false);
      onReview?.(drugs);
    }, 1000);
  };

  return (
    <div className="space-y-3">
      <div className="text-sm text-muted-foreground">
        添加患者当前用药，提交后进行相互作用与 Beers 标准审查（mock）。
      </div>

      {/* 添加表单 */}
      <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <Input
            placeholder="药物名称（如：氨氯地平）"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={cn("h-9", seniorMode && "h-11 text-base")}
            aria-label="药物名称"
          />
          <Input
            placeholder="剂量（如：5mg）"
            value={dosage}
            onChange={(e) => setDosage(e.target.value)}
            className={cn("h-9", seniorMode && "h-11 text-base")}
            aria-label="剂量"
          />
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="频次（如：每日 1 次）"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
            className={cn("flex-1 h-9", seniorMode && "h-11 text-base")}
            aria-label="频次"
          />
          <Button
            onClick={handleAdd}
            disabled={!name.trim()}
            className="gap-1 shrink-0"
            aria-label="添加药物"
          >
            <Plus className="size-4" />
            添加
          </Button>
        </div>
      </div>

      {/* 已添加药物列表 */}
      {drugs.length > 0 ? (
        <div className="space-y-1.5">
          <div className="text-xs text-muted-foreground">
            已添加 {drugs.length} 种药物
          </div>
          {drugs.map((d) => (
            <div
              key={d.id}
              className="flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5"
            >
              <Pill className="size-3.5 text-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{d.name}</div>
                <div className="text-[11px] text-muted-foreground truncate">
                  {[d.dosage, d.frequency].filter(Boolean).join(" · ")}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleRemove(d.id)}
                className="p-1 rounded text-muted-foreground hover:text-destructive shrink-0"
                aria-label={`移除 ${d.name}`}
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-6 text-xs text-muted-foreground">
          暂未添加药物
        </div>
      )}

      {/* 提交审查 */}
      <Button
        onClick={handleReview}
        disabled={drugs.length === 0 || reviewing}
        className="w-full gap-1"
      >
        {reviewing ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            正在审查…
          </>
        ) : (
          <>开始用药审查</>
        )}
      </Button>
    </div>
  );
}
