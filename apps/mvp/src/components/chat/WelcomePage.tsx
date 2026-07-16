"use client";

import { useState, useEffect } from "react";
import {
  ClipboardCheck,
  FileSearch,
  Pill,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatActionType, Role } from "@/types";
import { useAppStore } from "@/stores/appStore";

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
  role: propRole,
  seniorMode: propSeniorMode,
}: WelcomePageProps) {
  const [mounted, setMounted] = useState(false);
  const storeRole = useAppStore((s) => s.role);
  const storeSeniorMode = useAppStore((s) => s.seniorMode);
  const setRole = useAppStore((s) => s.setRole);
  
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  const role = mounted ? (propRole ?? storeRole) : "visitor";
  const seniorMode = mounted ? (propSeniorMode ?? storeSeniorMode) : false;
  
  const isPatient = role === "patient";
  const isDoctor = role === "doctor";
  const isVisitor = role === "visitor";

  const greeting = isVisitor
    ? "欢迎使用 GerClaw 老年科AI诊疗平台"
    : isPatient
    ? "您好，我是 GerClaw 健康助手，有什么可以帮您？"
    : "您好，GerClaw 辅助诊疗已就绪";

  const subtitle = isVisitor
    ? "请选择您的使用模式开始体验"
    : isPatient
    ? "您可以文字或语音描述健康问题，我会尽力帮助您。"
    : "可检索循证资料、完成可用的 CGA 量表，或安全记录待审核信息。";

  // 患者端快捷卡片：两大功能入口
  const patientCards = [
    {
      icon: Pill,
      label: "五大处方信息收集",
      desc: "保存健康信息；当前不生成医疗建议",
      action: "prescription" as const,
    },
    {
      icon: ClipboardCheck,
      label: "综合评估（CGA）",
      desc: "CGA 多维度健康评估",
      action: "cga" as const,
    },
    {
      icon: UserRound,
      label: "我的健康记录",
      desc: "查看已确认的个人健康信息",
      action: "health-profile" as const,
    },
  ];

  // 医生端快捷卡片：四大功能
  const doctorCards = [
    {
      icon: Pill,
      label: "五大处方信息收集",
      desc: "记录处方所需信息；当前不生成处方建议",
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
      label: "用药信息收集",
      desc: "记录用药信息；当前不输出审查结论",
      action: "drug-review" as const,
    },
    {
      icon: UserRound,
      label: "我的健康记录",
      desc: "查看本人已确认的健康信息",
      action: "health-profile" as const,
    },
  ];

  // 访客模式：选择角色卡片
  const visitorCards = [
    {
      icon: UserRound,
      label: "我是老年朋友",
      desc: "适老化界面，语音交互，通俗易懂",
      role: "patient" as Role,
      color: "bg-primary/10 text-primary",
    },
    {
      icon: Stethoscope,
      label: "我是医生",
      desc: "专业医学界面，循证规范，高效辅助",
      role: "doctor" as Role,
      color: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300",
    },
  ];

  const quickCards = isPatient ? patientCards : isDoctor ? doctorCards : [];

  const examples = isPatient
    ? [
        "我最近血压偏高怎么办？",
        "头晕乏力是什么原因？",
        "糖尿病饮食要注意什么？",
        "我正在吃降压药和他汀，需要注意什么？",
      ]
    : isDoctor
    ? [
        "如何整理患者的用药信息供后续核对？",
        "如何开始老年综合评估（CGA）？",
        "查找老年高血压管理最新指南",
        "多病共存患者有哪些需要关注的健康信息？",
      ]
    : [
        "GerClaw有哪些功能？",
        "如何使用老年综合评估？",
        "五大处方包含什么内容？",
      ];

  const handleSelectRole = (selectedRole: Role) => {
    setRole(selectedRole);
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 py-6 sm:py-10 flex flex-col items-center text-center">
        {/* Logo */}
        <div className="flex items-center justify-center size-14 sm:size-16 rounded-2xl bg-primary text-primary-foreground mb-3 sm:mb-4">
          <Stethoscope className="size-8" />
        </div>

        {/* 问候语 */}
        <h1
          className={cn(
            "font-bold text-foreground mb-2",
            seniorMode ? "text-2xl leading-tight sm:text-3xl" : "text-2xl"
          )}
        >
          {greeting}
        </h1>
        <p className={cn("text-muted-foreground mb-5 sm:mb-8", seniorMode ? "text-lg leading-8" : "text-sm")}>
          {subtitle}
        </p>

        {/* 访客模式：角色选择 */}
        {isVisitor && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full mb-8">
            {visitorCards.map((card) => (
              <button
                key={card.role}
                type="button"
                onClick={() => handleSelectRole(card.role)}
                className="flex flex-col items-start gap-3 rounded-xl border-2 border-border bg-card p-6 text-left hover:border-primary/40 hover:bg-muted/30 transition-all"
              >
                <div className={cn("flex items-center justify-center size-12 rounded-xl", card.color)}>
                  <card.icon className="size-6" />
                </div>
                <div>
                  <div className="font-semibold text-lg">
                    {card.label}
                  </div>
                  <div className="text-sm text-muted-foreground mt-1">
                    {card.desc}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* 功能快捷入口（患者/医生模式）*/}
        {!isVisitor && (
          <div className={cn("grid gap-3 w-full mb-8", seniorMode ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-2")}>
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
                  <div className={cn("text-muted-foreground mt-0.5", seniorMode ? "text-lg leading-7" : "text-xs")}>
                    {card.desc}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* 示例提示词 */}
        <div className="w-full">
          <div className={cn("text-muted-foreground mb-2 text-left", seniorMode ? "text-lg" : "text-xs")}>
            {isVisitor ? "了解平台功能：" : "您可以试试以下提问："}
          </div>
          <div className="flex flex-col gap-2">
            {examples.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => onExampleClick?.(ex)}
                className={cn(
                  "text-left text-sm rounded-lg border border-border bg-muted/40 px-4 py-2.5 hover:bg-muted hover:border-primary/40 transition-colors",
                  seniorMode && "text-lg py-3"
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
