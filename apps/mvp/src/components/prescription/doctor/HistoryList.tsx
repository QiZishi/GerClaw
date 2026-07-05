"use client";

import { useState } from "react";
import { ChevronRight, Clock, FileText, Filter } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 处方历史记录条目 */
export interface PrescriptionHistoryItem {
  id: string;
  patientName: string;
  patientId: string;
  title: string;
  status: "approved" | "rejected" | "draft";
  createdAt: number;
  reviewedAt?: number;
  reviewedBy?: string;
  rejectReason?: string;
  summary: string;
}

interface HistoryListProps {
  items?: PrescriptionHistoryItem[];
  className?: string;
  onSelect?: (item: PrescriptionHistoryItem) => void;
}

const DEFAULT_MOCK_HISTORY: PrescriptionHistoryItem[] = [
  {
    id: "rx_h_001",
    patientName: "张桂芳",
    patientId: "p001",
    title: "五大处方 · 高血压+糖尿病综合干预",
    status: "approved",
    createdAt: Date.now() - 2 * 24 * 60 * 60 * 1000,
    reviewedAt: Date.now() - 2 * 24 * 60 * 60 * 1000 + 30 * 60 * 1000,
    reviewedBy: "Dr. Wang（mock）",
    summary: "调整降压方案为氨氯地平 5mg qd，维持二甲双胍与他汀治疗。",
  },
  {
    id: "rx_h_002",
    patientName: "李建国",
    patientId: "p002",
    title: "五大处方 · 冠心病二级预防",
    status: "approved",
    createdAt: Date.now() - 5 * 24 * 60 * 60 * 1000,
    reviewedAt: Date.now() - 5 * 24 * 60 * 60 * 1000 + 60 * 60 * 1000,
    reviewedBy: "Dr. Wang（mock）",
    summary: "阿司匹林+他汀+美托洛尔方案维持，加强运动与营养干预。",
  },
  {
    id: "rx_h_003",
    patientName: "王秀兰",
    patientId: "p003",
    title: "五大处方 · 跌倒风险综合干预",
    status: "rejected",
    createdAt: Date.now() - 7 * 24 * 60 * 60 * 1000,
    reviewedAt: Date.now() - 7 * 24 * 60 * 60 * 1000 + 45 * 60 * 1000,
    reviewedBy: "Dr. Wang（mock）",
    rejectReason: "运动处方强度过高，需调整为更温和的方案",
    summary: "针对跌倒风险与认知下降制定综合康复方案。",
  },
  {
    id: "rx_h_004",
    patientName: "赵德顺",
    patientId: "p004",
    title: "五大处方 · 糖尿病随访",
    status: "approved",
    createdAt: Date.now() - 10 * 24 * 60 * 60 * 1000,
    reviewedAt: Date.now() - 10 * 24 * 60 * 60 * 1000 + 20 * 60 * 1000,
    reviewedBy: "Dr. Wang（mock）",
    summary: "维持当前降糖方案，加强血糖监测与饮食指导。",
  },
  {
    id: "rx_h_005",
    patientName: "陈美珍",
    patientId: "p005",
    title: "五大处方 · 焦虑伴睡眠障碍",
    status: "draft",
    createdAt: Date.now() - 1 * 24 * 60 * 60 * 1000,
    summary: "针对焦虑与睡眠障碍的心理+药物综合处方（待审核）。",
  },
];

type FilterKey = "all" | PrescriptionHistoryItem["status"];

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "approved", label: "已审核" },
  { key: "rejected", label: "已驳回" },
  { key: "draft", label: "待审核" },
];

/**
 * §医生端 处方历史列表
 * 按时间倒序展示历史处方，支持按状态筛选
 */
export function HistoryList({
  items = DEFAULT_MOCK_HISTORY,
  className,
  onSelect,
}: HistoryListProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [filter, setFilter] = useState<FilterKey>("all");

  const filtered =
    filter === "all" ? items : items.filter((i) => i.status === filter);

  return (
    <div className={cn("flex flex-col h-full", className)}>
      <header className="px-3 py-2 border-b border-border">
        <h3
          className={cn(
            "font-medium flex items-center gap-1.5 mb-2",
            seniorMode ? "text-base" : "text-sm"
          )}
        >
          <Clock className="size-4" />
          处方历史
        </h3>
        <div className="flex items-center gap-1 flex-wrap">
          <Filter className="size-3 text-muted-foreground" />
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={cn(
                "text-[11px] px-1.5 py-0.5 rounded transition-colors",
                filter === f.key
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/70"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      <ScrollArea className="flex-1 min-h-0">
        <ul className="p-2 space-y-1.5">
          {filtered.length === 0 && (
            <li className="text-center text-xs text-muted-foreground py-8">
              暂无相关历史记录
            </li>
          )}
          {filtered.map((item) => (
            <HistoryListItem
              key={item.id}
              item={item}
              seniorMode={seniorMode}
              onSelect={() => onSelect?.(item)}
            />
          ))}
        </ul>
      </ScrollArea>
    </div>
  );
}

interface HistoryListItemProps {
  item: PrescriptionHistoryItem;
  seniorMode: boolean;
  onSelect: () => void;
}

function HistoryListItem({
  item,
  seniorMode,
  onSelect,
}: HistoryListItemProps) {
  const variant =
    item.status === "approved"
      ? "secondary"
      : item.status === "rejected"
        ? "destructive"
        : "outline";

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className="w-full text-left rounded-lg border border-border bg-card px-3 py-2 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-start gap-2">
          <FileText className="size-4 shrink-0 text-muted-foreground mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={cn(
                  "font-medium truncate",
                  seniorMode ? "text-sm" : "text-xs"
                )}
              >
                {item.title}
              </span>
              <Badge variant={variant} className="text-[10px] py-0 shrink-0">
                {statusLabel(item.status)}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
              {item.summary}
            </p>
            <Separator className="my-1.5" />
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>{item.patientName}</span>
              <span>{formatRelativeTime(item.createdAt)}</span>
            </div>
            {item.status === "rejected" && item.rejectReason && (
              <p className="mt-1.5 text-[11px] text-destructive leading-relaxed">
                驳回原因：{item.rejectReason}
              </p>
            )}
            {item.reviewedAt && (
              <p className="mt-1 text-[10px] text-muted-foreground">
                审核时间：{formatDateTime(item.reviewedAt)}
                {item.reviewedBy ? ` · ${item.reviewedBy}` : ""}
              </p>
            )}
          </div>
          <ChevronRight className="size-3.5 text-muted-foreground shrink-0 mt-1" />
        </div>
      </button>
    </li>
  );
}

function statusLabel(status: PrescriptionHistoryItem["status"]): string {
  switch (status) {
    case "approved":
      return "已审核";
    case "rejected":
      return "已驳回";
    case "draft":
      return "待审核";
  }
}
