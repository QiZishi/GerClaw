"use client";

import {
  ClipboardCheck,
  FileSearch,
  Pill,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatActionType } from "@/types";

interface WelcomePageProps {
  onExampleClick?: (text: string) => void;
  /** 点击功能快捷入口：触发对应功能模式（在聊天区对话式收集信息）*/
  onStartAction?: (action: ChatActionType) => void;
  /** 当前角色 */
  role?: "patient" | "doctor" | "visitor";
  /** 老年模式 */
  seniorMode?: boolean;
}

/**
 * §3.3.1 欢迎页
 * 中央：Logo + 问候语 + 功能快捷入口卡片 + 示例提示词
 * 快捷入口点击后通过 onStartAction 触发中间栏对话式功能流程，而非跳转右侧面板
 */
export function WelcomePage({
  onExampleClick,
  onStartAction,
  role = "patient",
  seniorMode = false,
}: WelcomePageProps) {
  const isPatient = role !== "doctor";
  const greeting = isPatient
    ? "您好，我是 GerClaw 健康助手，有什么可以帮您？"
    : "您好，GerClaw 辅助诊疗已就绪";

  // 患者端快捷卡片：五大处方、CGA、健康画像（患者管理自己的档案）
  const patientCards = [
    {
      icon: Pill,
      label: "五大处方生成",
      desc: "用药、运动、营养、心理、康复",
      action: "prescription" as const,
    },
    {
      icon: ClipboardCheck,
      label: "老年综合评估",
      desc: "CGA 多维度健康评估",
      action: "cga" as const,
    },
    {
      icon: UserRound,
      label: "我的健康画像",
      desc: "查看和管理我的健康档案",
      action: "health-profile" as const,
    },
  ];

  // 医生端快捷卡片：四大功能（用药审查为医生端专用）
  const doctorCards = [
    {
      icon: Pill,
      label: "五大处方生成",
      desc: "为患者生成多维度处方",
      action: "prescription" as const,
    },
    {
      icon: ClipboardCheck,
      label: "老年综合评估",
      desc: "CGA 多维度评估",
      action: "cga" as const,
    },
    {
      icon: FileSearch,
      label: "用药审查",
      desc: "审查多药相互作用与 Beers 标准",
      action: "drug-review" as const,
    },
    {
      icon: UserRound,
      label: "查看健康画像",
      desc: "查询患者健康档案",
      action: "health-profile" as const,
    },
  ];

  const quickCards = isPatient ? patientCards : doctorCards;

  const examples = isPatient
    ? [
        "我最近血压偏高怎么办？",
        "头晕乏力是什么原因？",
        "糖尿病饮食要注意什么？",
        "这些药可以一起吃吗？",
      ]
    : [
        "帮我分析这位患者的用药方案",
        "生成老年综合评估报告",
        "查找老年高血压管理最新指南",
        "评估多病共存患者的用药风险",
      ];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 py-10 flex flex-col items-center text-center">
        {/* Logo */}
        <div className="flex items-center justify-center size-16 rounded-2xl bg-primary text-primary-foreground mb-4">
          <Stethoscope className="size-8" />
        </div>

        {/* 问候语 */}
        <h1
          className={cn(
            "font-bold text-foreground mb-2",
            seniorMode ? "text-3xl" : "text-2xl"
          )}
        >
          {greeting}
        </h1>
        <p className="text-muted-foreground text-sm mb-8">
          {isPatient
            ? "您可以文字或语音描述健康问题，我会尽力帮助您。"
            : "可辅助您完成诊疗决策、用药评估、CGA 评估等任务。"}
        </p>

        {/* 功能快捷入口 */}
        <div className="grid grid-cols-2 gap-3 w-full mb-8">
          {quickCards.map((card) => (
            <button
              key={card.label}
              type="button"
              onClick={() => onStartAction?.(card.action)}
              className={cn(
                "flex flex-col items-start gap-2 rounded-xl border border-border bg-card p-4 text-left hover:bg-muted/50 hover:border-primary/40 transition-colors",
                seniorMode && "p-5"
              )}
              data-quick-card
            >
              <div className="flex items-center justify-center size-10 rounded-lg bg-primary/10 text-primary">
                <card.icon className="size-5" />
              </div>
              <div>
                <div
                  className={cn(
                    "font-medium",
                    seniorMode ? "text-lg" : "text-base"
                  )}
                >
                  {card.label}
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {card.desc}
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* 示例提示词 */}
        <div className="w-full">
          <div className="text-xs text-muted-foreground mb-2 text-left">
            您可以试试以下提问：
          </div>
          <div className="flex flex-col gap-2">
            {examples.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => onExampleClick?.(ex)}
                className={cn(
                  "text-left text-sm rounded-lg border border-border bg-muted/40 px-4 py-2.5 hover:bg-muted hover:border-primary/40 transition-colors",
                  seniorMode && "text-base py-3"
                )}
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
