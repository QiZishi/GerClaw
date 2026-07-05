"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { PatientSummary } from "@/types";

interface CollectionFormProps {
  /** 提交回调，传入收集到的患者信息 */
  onComplete?: (data: PatientSummary) => void;
  /** 取消回调 */
  onCancel?: () => void;
}

/**
 * §6 五大处方 — 信息收集表单
 * 年龄/性别/主诉/合并症/当前用药/过敏史/生活方式
 * 所有输入用 mock 存储，提交后触发 onComplete
 */
export function CollectionForm({ onComplete, onCancel }: CollectionFormProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);

  const [form, setForm] = useState({
    age: "",
    gender: "male" as "male" | "female",
    chiefComplaint: "",
    history: "",
    currentMedications: "",
    allergies: "",
    lifestyle: "",
  });

  const update = <K extends keyof typeof form>(
    key: K,
    value: (typeof form)[K]
  ) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const handleSubmit = () => {
    const data: PatientSummary = {
      age: form.age ? Number(form.age) : undefined,
      gender: form.gender,
      chiefComplaint: form.chiefComplaint || undefined,
      history: form.history
        ? form.history.split(/[、,，\n]/).map((s) => s.trim()).filter(Boolean)
        : undefined,
      currentMedications: form.currentMedications
        ? form.currentMedications
            .split(/[、,，\n]/)
            .map((s) => s.trim())
            .filter(Boolean)
        : undefined,
      allergies: form.allergies
        ? form.allergies.split(/[、,，\n]/).map((s) => s.trim()).filter(Boolean)
        : undefined,
      vitals: form.lifestyle
        ? { 生活方式: form.lifestyle }
        : undefined,
    };
    onComplete?.(data);
  };

  const inputCls = cn("h-9", seniorMode && "h-11 text-base");
  const labelCls = cn("text-sm", seniorMode && "text-base");

  return (
    <div className="flex flex-col gap-4">
      <div className="text-sm text-muted-foreground">
        请填写以下患者信息，用于生成五大处方。所有数据仅在本地处理（mock）。
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cf-age" className={labelCls}>
            年龄 <span className="text-destructive">*</span>
          </Label>
          <Input
            id="cf-age"
            type="number"
            inputMode="numeric"
            placeholder="如：78"
            value={form.age}
            onChange={(e) => update("age", e.target.value)}
            className={inputCls}
            aria-required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className={labelCls}>性别</Label>
          <div className="flex gap-2">
            {(["male", "female"] as const).map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => update("gender", g)}
                className={cn(
                  "flex-1 h-9 rounded-md border text-sm transition-colors",
                  seniorMode && "h-11 text-base",
                  form.gender === g
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border bg-background hover:bg-muted"
                )}
                aria-pressed={form.gender === g}
              >
                {g === "male" ? "男" : "女"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cf-cc" className={labelCls}>
          主诉 <span className="text-destructive">*</span>
        </Label>
        <Input
          id="cf-cc"
          placeholder="如：血压偏高伴头晕乏力 1 月余"
          value={form.chiefComplaint}
          onChange={(e) => update("chiefComplaint", e.target.value)}
          className={inputCls}
          aria-required
        />
      </div>

      <Separator />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cf-hx" className={labelCls}>
          合并症（用顿号/逗号分隔）
        </Label>
        <Input
          id="cf-hx"
          placeholder="如：高血压、糖尿病、骨质疏松"
          value={form.history}
          onChange={(e) => update("history", e.target.value)}
          className={inputCls}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cf-med" className={labelCls}>
          当前用药（用顿号/换行分隔）
        </Label>
        <textarea
          id="cf-med"
          placeholder={"如：\n氨氯地平 5mg qd\n二甲双胍 0.5g bid"}
          value={form.currentMedications}
          onChange={(e) => update("currentMedications", e.target.value)}
          rows={3}
          className={cn(
            "w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
            seniorMode && "text-base py-2.5"
          )}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cf-allergy" className={labelCls}>
          过敏史
        </Label>
        <Input
          id="cf-allergy"
          placeholder="如：青霉素过敏 / 无"
          value={form.allergies}
          onChange={(e) => update("allergies", e.target.value)}
          className={inputCls}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cf-life" className={labelCls}>
          生活方式（饮食/运动/睡眠）
        </Label>
        <Input
          id="cf-life"
          placeholder="如：饮食偏咸，少运动，睡眠差"
          value={form.lifestyle}
          onChange={(e) => update("lifestyle", e.target.value)}
          className={inputCls}
        />
      </div>

      <div className="flex items-center justify-end gap-2 pt-2">
        {onCancel && (
          <Button variant="outline" onClick={onCancel}>
            取消
          </Button>
        )}
        <Button
          onClick={handleSubmit}
          disabled={!form.age || !form.chiefComplaint}
          className="gap-1"
        >
          <Check className="size-4" />
          提交并生成处方
        </Button>
      </div>
    </div>
  );
}
