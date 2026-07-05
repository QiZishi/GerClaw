"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { WelcomePage } from "@/components/chat/WelcomePage";
import { SkillManager } from "@/components/skills/SkillManager";
import { ScaleSelector } from "@/components/cga/ScaleSelector";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { scales } from "@/data/scales";
import { cn } from "@/lib/utils";
import { HIGH_RISK_SYMPTOMS, EMERGENCY_ALERT, MEDICAL_DISCLAIMER } from "@/lib/constants";
import { postprocessMedicalText } from "@/lib/security-postprocess";
import { streamChat, buildSystemPrompt, type LLMMessage } from "@/services/llm";
import { search } from "@/services/search/search-client";
import type { ChatActionType, Message, MessageBlock, Scale, ScaleQuestion, SearchResultItem } from "@/types";
import { generateId } from "@/lib/format";

/** 检测文本中是否包含高风险症状关键词（铁律5关联） */
function detectHighRiskSymptoms(text: string): string[] {
  const matched: string[] = [];
  for (const kw of HIGH_RISK_SYMPTOMS) {
    if (text.includes(kw)) matched.push(kw);
  }
  return matched;
}

const SEARCH_KEYWORDS = ["搜索", "查一下", "最新", "指南", "查一查", "搜一下", "帮我查", "最新的", "最新指南", "检索"];

function detectSearchNeed(text: string): boolean {
  return SEARCH_KEYWORDS.some((kw) => text.includes(kw));
}

function formatSearchResultsForLLM(results: SearchResultItem[]): string {
  if (results.length === 0) return "";
  const lines = results.map((r, i) => {
    return `[${i + 1}] ${r.title}\n来源：${r.source}\n链接：${r.url}\n摘要：${r.snippet}`;
  });
  return `\n\n以下是联网搜索到的相关参考资料，请基于这些资料回答用户问题，并在回答中自然引用来源编号（如"根据资料[1]..."）：\n\n${lines.join("\n\n")}\n`;
}

/** 构建高风险症状立即就医强提示消息 */
function buildEmergencyMessage(matched: string[], role: "patient" | "doctor" | "visitor"): Message {
  const list = matched.join("、");
  const content =
    role === "doctor"
      ? `⚠️ ${EMERGENCY_ALERT}\n\n检测到以下高风险症状：${list}。建议立即安排急诊评估，不要延误。`
      : `⚠️ ${EMERGENCY_ALERT}\n\n您提到的"${list}"可能是严重疾病的信号，请立即拨打 120 或前往最近的医院急诊就诊，不要自行处理或等待症状缓解。`;
  return {
    id: generateId("msg"),
    sessionId: "",
    role: "assistant",
    blocks: [
      {
        kind: "text",
        id: generateId("block"),
        content,
      },
    ],
    status: "done",
    createdAt: Date.now(),
    hasDisclaimer: true,
  };
}

/** 获取功能的开场消息（患者端 vs 医生端不同话术）*/
function getOpeningMessage(
  action: ChatActionType,
  role: "patient" | "doctor" | "visitor",
  scaleName?: string
): string {
  const isPatient = role !== "doctor";
  switch (action) {
    case "prescription":
      return isPatient
        ? "好的～我来帮您生成个性化的五大处方建议（包括用药、运动、营养、心理和康复五个方面）。您可以像平时聊天一样跟我说您的情况，也可以上传病历或检查报告，我会自动帮您整理信息。如果我觉得信息还不够，会主动问您的。\n\n首先想了解一下，您今年多大年纪啦？是男性还是女性？目前哪里不舒服呢？"
        : "好的，开始为患者生成五大处方（药物/运动/营养/心理/康复）。请直接描述患者情况或上传病历、检查报告，系统将自动提取所需信息。信息不足时会主动追问。\n\n请提供患者年龄、性别、主诉。";
    case "cga": {
      const scaleInfo = scaleName ? `（${scaleName}）` : "";
      return isPatient
        ? `好的，我们来做${scaleInfo}评估。这个评估会问您几个简单的问题，您慢慢回答就好，我会根据您的回答给出评估结果。\n\n首先想了解一下，您今年多大年纪啦？`
        : `开始${scaleInfo}评估。请上传评估资料或输入患者信息，系统将结合量表条目进行对话式评估。信息不足时会主动追问。\n\n请提供患者年龄与基本情况。`;
    }
    case "drug-review":
      return isPatient
        ? "好的，我来帮您审查用药方案。请告诉我您正在吃的所有药物（药名、剂量、频次），我会检查有没有药物相互作用或者不适合老年人的药。\n\n请先告诉我您现在在吃哪些药？"
        : "开始用药审查。请添加患者当前用药（名称、剂量、频次、途径），系统将进行 Beers 标准与药物相互作用审查。可上传处方单图片。";
    case "health-profile":
      return isPatient
        ? "好的，正在为您调取个人健康档案，请稍候…"
        : "请输入患者姓名或身份证号查询健康档案。";
    default:
      return "";
  }
}

/**
 * §3.3 中间聊天区
 * 弹性宽度，根据 mainView 切换显示聊天或技能管理
 * - mainView='chat'：无消息显示欢迎页，否则显示消息列表 + 输入框
 * - mainView='skills'：显示技能管理（对齐 Trae Work）
 * - chatAction：对话式功能流程（AI 通过聊天收集用户信息，自动提取+追问）
 */
export function ChatArea() {
  const role = useAppStore((s) => s.role);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const mainView = useAppStore((s) => s.mainView);
  const setMainView = useAppStore((s) => s.setMainView);
  const chatAction = useAppStore((s) => s.chatAction);
  const setChatAction = useAppStore((s) => s.setChatAction);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setPanelContent = useAppStore((s) => s.setPanelContent);
  const appendPanelContent = useAppStore((s) => s.appendPanelContent);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const setGenerating = useChatStore((s) => s.setGenerating);
  const messagesBySession = useChatStore((s) => s.messagesBySession);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const removeMessage = useChatStore((s) => s.removeMessage);
  const updateSession = useChatStore((s) => s.updateSession);
  const createSession = useChatStore((s) => s.createSession);
  const storeSessions = useChatStore((s) => s.sessions);

  const abortControllerRef = useRef<AbortController | null>(null);

  // 各会话功能模式下的对话轮次计数（sessionId -> count），上限5轮
  const [collectRounds, setCollectRounds] = useState<Record<string, number>>({});
  const MAX_COLLECT_ROUNDS = 5;
  const actionInitRef = useRef<string | null>(null);

  // CGA：当前会话已选择的评估量表（sessionId -> Scale.id）
  const [cgaSelectedScale, setCgaSelectedScale] = useState<
    Record<string, string>
  >({});

  // CGA：答题状态（sessionId -> { questionId: value | value[] }）
  const [cgaAnswers, setCgaAnswers] = useState<
    Record<string, Record<string, number | number[]>>
  >({});
  // CGA：当前题号（sessionId -> index）
  const [cgaCurrentIndex, setCgaCurrentIndex] = useState<
    Record<string, number>
  >({});
  // CGA：是否已完成答题（sessionId -> boolean）
  const [cgaCompleted, setCgaCompleted] = useState<Record<string, boolean>>(
    {}
  );
  // 老年模式退出功能二次确认弹窗
  const [showExitConfirm, setShowExitConfirm] = useState(false);

  const messages: Message[] = currentSessionId
    ? messagesBySession[currentSessionId] ?? []
    : [];

  const currentSessionTitle = (() => {
    if (!currentSessionId) return "";
    const fromStore = storeSessions.find((s) => s.id === currentSessionId);
    return fromStore?.title ?? "";
  })();

  /** 从消息中提取纯文本内容 */
  const getTextFromMessage = (msg: Message): string => {
    return msg.blocks
      .filter((b): b is Extract<MessageBlock, { kind: "text" }> => b.kind === "text")
      .map((b) => b.content)
      .join("\n");
  };

  useEffect(() => {
    if (!currentSessionId) return;
    actionInitRef.current = null;
  }, [currentSessionId]);

  // 当 chatAction 变化时：自动创建会话（如需要）；非 CGA 直接发开场消息
  useEffect(() => {
    if (chatAction === "none") {
      actionInitRef.current = null;
      return;
    }

    // 确保有会话
    let sid = currentSessionId;
    if (!sid) {
      sid = createSession(role);
      setCurrentSession(sid);
    }

    // CGA 走答题流程，不走对话开场消息
    if (chatAction === "cga") {
      actionInitRef.current = null;
      return;
    }

    if (chatAction === "health-profile" && role !== "doctor") {
      const initKey = `${sid}:health-profile-patient`;
      if (actionInitRef.current === initKey) return;
      actionInitRef.current = initKey;
      setGenerating(true);
      setTimeout(() => {
        const aiMsg: Message = {
          id: generateId("msg"),
          sessionId: sid!,
          role: "assistant",
          blocks: [
            {
              kind: "text",
              id: generateId("block"),
              content: postprocessMedicalText("好的，您的健康档案如下，请过目。如果有需要补充或修改的信息，随时告诉我。"),
            },
          ],
          status: "done",
          createdAt: Date.now(),
          hasDisclaimer: true,
        };
        addMessage(aiMsg);
        setGenerating(false);
      }, 300);
      return;
    }

    const initKey = `${sid}:${chatAction}`;
    if (actionInitRef.current === initKey) return;
    actionInitRef.current = initKey;

    // prescription 和 drug-review 使用 LLM 生成开场消息
    if (chatAction === "prescription" || chatAction === "drug-review") {
      setGenerating(true);
      setPanelContent("");
      
      const assistantMsgId = generateId("msg");
      const assistantBlockId = generateId("block");
      
      let systemPrompt = "";
      if (chatAction === "prescription") {
        systemPrompt = role === "doctor"
          ? "你是GerClaw老年科医生AI助手，正在协助医生生成五大处方。请专业简洁地开场，告诉医生你将通过对话收集患者信息，一次问1-2个关键问题。"
          : "你是GerClaw老年科AI医生助手，正在为老年患者生成五大处方（药物处方、运动处方、营养处方、心理处方、康复处方）。请通过亲切自然的对话了解患者情况，像聊天一样一次只问1-2个问题，开场请先问候并了解基本情况（年龄、性别、主要不适）。";
      } else {
        systemPrompt = role === "doctor"
          ? "你是GerClaw老年科医生AI助手，正在协助医生进行用药审查。请专业简洁地开场，告诉医生你需要了解用药清单（药名/剂量/频次）、诊断、不良反应等信息。"
          : "你是GerClaw老年科AI医生助手，正在为老年患者进行用药审查。请亲切地开场，告诉患者你需要了解正在吃的药（药名、每次吃多少、一天吃几次）、治什么病、吃药后有没有不舒服。";
      }

      const llmMessages: LLMMessage[] = [
        { role: "system", content: systemPrompt },
        { role: "user", content: "开始" }
      ];

      const assistantMsg: Message = {
        id: assistantMsgId,
        sessionId: sid!,
        role: "assistant",
        blocks: [
          {
            kind: "text",
            id: assistantBlockId,
            content: "",
            streaming: true,
          },
        ],
        status: "streaming",
        createdAt: Date.now(),
        hasDisclaimer: false,
      };
      addMessage(assistantMsg);

      setTimeout(() => {
        setCollectRounds((prev) => ({ ...prev, [sid!]: 0 }));
      }, 0);

      abortControllerRef.current = new AbortController();

      streamChat(
        llmMessages,
        { signal: abortControllerRef.current.signal },
        {
          onText: (_delta, fullText) => {
            updateMessage(assistantMsgId, {
              blocks: [
                {
                  kind: "text",
                  id: assistantBlockId,
                  content: fullText,
                  streaming: true,
                },
              ],
            });
          },
          onDone: (fullText) => {
            abortControllerRef.current = null;
            const finalContent = postprocessMedicalText(fullText);
            updateMessage(assistantMsgId, {
              status: "done",
              blocks: [
                {
                  kind: "text",
                  id: assistantBlockId,
                  content: finalContent,
                  streaming: false,
                },
              ],
              hasDisclaimer: true,
            });
            setGenerating(false);
          },
          onError: () => {
            abortControllerRef.current = null;
            const fallbackContent = getOpeningMessage(chatAction, role);
            updateMessage(assistantMsgId, {
              status: "done",
              blocks: [
                {
                  kind: "text",
                  id: assistantBlockId,
                  content: postprocessMedicalText(fallbackContent),
                  streaming: false,
                },
              ],
              hasDisclaimer: true,
            });
            setGenerating(false);
          },
        }
      );
      return;
    }

    // 其他功能暂时使用硬编码开场（保留原有逻辑）
    setGenerating(true);
    setTimeout(() => {
      const aiMsg: Message = {
        id: generateId("msg"),
        sessionId: sid!,
        role: "assistant",
        blocks: [
          {
            kind: "text",
            id: generateId("block"),
            content: postprocessMedicalText(getOpeningMessage(chatAction, role)),
          },
        ],
        status: "done",
        createdAt: Date.now(),
        hasDisclaimer: true,
      };
      addMessage(aiMsg);
      setGenerating(false);
    }, 300);
  }, [chatAction, currentSessionId, role, createSession, setCurrentSession, addMessage, setGenerating, cgaSelectedScale, setPanelContent, updateMessage, appendPanelContent]);

  // 技能管理视图
  if (mainView === "skills") {
    return (
      <main className="flex-1 flex flex-col min-w-0 bg-background">
        <header
          className="sticky top-0 z-10 flex items-center gap-2 px-3 h-12 border-b border-border bg-background/95 backdrop-blur"
          style={sidebarCollapsed ? { paddingLeft: "112px" } : undefined}
        >
          <Button
            variant="ghost"
            size="icon-sm"
            className="btn-icon shrink-0"
            onClick={() => setMainView("chat")}
            aria-label="返回对话"
          >
            <ArrowLeft className="size-4" />
          </Button>
          <span className="font-medium">技能管理</span>
        </header>
        <div className="flex-1 min-h-0">
          <SkillManager />
        </div>
      </main>
    );
  }

  /** 首次AI回复完成后自动设置会话标题 */
  const trySetSessionTitle = (sid: string, firstUserText: string) => {
    const session = storeSessions.find((s) => s.id === sid);
    if (session && session.title === "新对话") {
      const title = firstUserText.slice(0, 20);
      updateSession(sid, { title });
    }
  };

  /** 停止生成 */
  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    const messages = currentSessionId ? messagesBySession[currentSessionId] ?? [] : [];
    const streamingMsg = messages.find((m) => m.status === "streaming");
    if (streamingMsg) {
      const blocks = streamingMsg.blocks.map((b) => {
        if (b.kind === "text" && b.streaming) {
          return { ...b, streaming: false };
        }
        return b;
      });
      updateMessage(streamingMsg.id, {
        status: "stopped",
        blocks,
      });
    }
    setGenerating(false);
  };

  /** 重新生成 */
  const handleRegenerate = (messageId: string) => {
    if (!currentSessionId) return;
    const messages = messagesBySession[currentSessionId] ?? [];
    const aiMsgIndex = messages.findIndex((m) => m.id === messageId);
    if (aiMsgIndex === -1) return;
    
    let userMsgIndex = aiMsgIndex - 1;
    while (userMsgIndex >= 0 && messages[userMsgIndex].role !== "user") {
      userMsgIndex--;
    }
    if (userMsgIndex < 0) return;
    
    const userMsg = messages[userMsgIndex];
    const userText = getTextFromMessage(userMsg);
    
    const messagesToRemove = messages.slice(userMsgIndex + 1, aiMsgIndex + 1);
    messagesToRemove.forEach((m) => removeMessage(m.id));
    
    doSend(currentSessionId, userText, true);
  };

  const handleSend = (text: string) => {
    if (!currentSessionId) {
      const sid = createSession(role);
      setCurrentSession(sid);
      setTimeout(() => doSend(sid, text), 50);
      return;
    }
    doSend(currentSessionId, text);
  };

  const doSend = (sid: string, text: string, isRegenerate = false) => {
    const userMsg: Message = {
      id: generateId("msg"),
      sessionId: sid,
      role: "user",
      blocks: [{ kind: "text", id: generateId("block"), content: text }],
      status: "done",
      createdAt: Date.now(),
    };
    if (!isRegenerate) {
      addMessage(userMsg);
    }
    setGenerating(true);

    const highRisk = detectHighRiskSymptoms(text);
    const hasHighRisk = highRisk.length > 0;

    if (hasHighRisk) {
      const emMsg = buildEmergencyMessage(highRisk, role);
      emMsg.sessionId = sid;
      addMessage(emMsg);
    }

    if (chatAction !== "none" && chatAction !== "cga") {
      const newRound = (collectRounds[sid] ?? 0) + 1;
      setCollectRounds((prev) => ({ ...prev, [sid]: newRound }));

      const assistantMsgId = generateId("msg");
      const assistantBlockId = generateId("block");

      const assistantMsg: Message = {
        id: assistantMsgId,
        sessionId: sid,
        role: "assistant",
        blocks: [
          {
            kind: "text",
            id: assistantBlockId,
            content: "",
            streaming: true,
          },
        ],
        status: "streaming",
        createdAt: Date.now(),
        hasDisclaimer: false,
      };
      addMessage(assistantMsg);

      const sessionMessages = messagesBySession[sid] ?? [];
      const recentMessages = sessionMessages.slice(-20);

      const buildActionMessages = (): LLMMessage[] => {
        const llmMessages: LLMMessage[] = [];
        
        let systemPrompt = "";
        const forceGenerate = newRound >= MAX_COLLECT_ROUNDS;
        
        if (chatAction === "prescription") {
          systemPrompt = role === "doctor"
            ? `你是GerClaw老年科医生AI助手，正在协助医生生成五大处方（药物处方、运动处方、营养处方、心理处方、康复处方）。请通过对话收集患者信息，一次只问1-2个关键问题。
当你认为收集到足够信息（年龄、性别、主要不适、既往病史、当前用药、过敏史）后，在回复末尾输出特殊标记 [生成处方]，然后生成完整的Markdown格式五大处方报告。
报告结构：# 五大处方建议 ## 一、药物处方 ## 二、运动处方 ## 三、营养处方 ## 四、心理处方 ## 五、康复处方，每个处方给出具体可执行的建议，包含循证依据和注意事项。
${forceGenerate ? "重要：已达到对话轮次上限，请立即输出 [生成处方] 标记并生成完整报告。" : ""}`
            : `你是GerClaw老年科AI医生助手，正在为老年患者生成五大处方（药物处方、运动处方、营养处方、心理处方、康复处方）。请通过亲切自然的对话了解患者情况，像聊天一样一次只问1-2个问题。
当你收集到足够信息（年龄、性别、主要不适、既往病史、当前用药、过敏史）后，在回复末尾输出特殊标记 [生成处方]，然后生成完整的Markdown格式五大处方报告。
报告结构：# 五大处方建议 ## 一、药物处方 ## 二、运动处方 ## 三、营养处方 ## 四、心理处方 ## 五、康复处方，每个处方给出具体可执行的建议。
${forceGenerate ? "重要：已达到对话轮次上限，请立即输出 [生成处方] 标记并生成完整报告。" : ""}`;
        } else if (chatAction === "drug-review") {
          systemPrompt = role === "doctor"
            ? `你是GerClaw老年科医生AI助手，正在协助医生进行用药审查。请通过对话收集用药信息（药名/剂量/频次、诊断、不良反应），一次只问1-2个关键问题。
当你认为收集到足够信息后，在回复末尾输出特殊标记 [生成审查]，然后生成结构化的Markdown审查报告。
报告必须以"⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。"开头。
报告结构：# 用药审查报告 ## 一、用药汇总 ## 二、潜在相互作用提示 ## 三、Beers标准提醒 ## 四、剂量建议 ## 五、就医建议。
${forceGenerate ? "重要：已达到对话轮次上限，请立即输出 [生成审查] 标记并生成完整报告。" : ""}`
            : `你是GerClaw老年科AI医生助手，正在为老年患者进行用药审查。请通过亲切自然的对话了解用药情况（药名/剂量/频次、治什么病、有没有不舒服），一次只问1-2个问题。
当你收集到足够信息后，在回复末尾输出特殊标记 [生成审查]，然后生成结构化的Markdown审查报告。
报告必须以"⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。"开头。
报告结构：# 用药审查报告 ## 一、用药汇总 ## 二、潜在相互作用提示 ## 三、老年人用药提醒 ## 四、建议 ## 五、就医提示。
${forceGenerate ? "重要：已达到对话轮次上限，请立即输出 [生成审查] 标记并生成完整报告。" : ""}`;
        }

        llmMessages.push({ role: "system", content: systemPrompt });

        for (const msg of recentMessages) {
          if (msg.id === assistantMsgId) continue;
          if (msg.role === "user") {
            llmMessages.push({ role: "user", content: getTextFromMessage(msg) });
          } else if (msg.role === "assistant") {
            const msgText = getTextFromMessage(msg);
            if (msgText) {
              llmMessages.push({ role: "assistant", content: msgText });
            }
          }
        }
        return llmMessages;
      };

      const finishMarker = chatAction === "prescription" ? "[生成处方]" : "[生成审查]";
      const panelType = chatAction as "prescription" | "drug-review";
      const buttonLabel = chatAction === "prescription" ? "查看完整处方" : "查看审查结果";

      abortControllerRef.current = new AbortController();

      streamChat(
        buildActionMessages(),
        { signal: abortControllerRef.current.signal },
        {
          onText: (_delta, fullText) => {
            updateMessage(assistantMsgId, {
              blocks: [
                {
                  kind: "text",
                  id: assistantBlockId,
                  content: fullText,
                  streaming: true,
                },
              ],
            });
          },
          onDone: (fullText) => {
            abortControllerRef.current = null;
            
            const hasFinishMarker = fullText.includes(finishMarker);
            let replyText = fullText;
            let reportContent = "";
            
            if (hasFinishMarker) {
              const parts = fullText.split(finishMarker);
              replyText = parts[0].trim();
              reportContent = parts.slice(1).join(finishMarker).trim();
            }

            const finalReplyContent = postprocessMedicalText(replyText);
            updateMessage(assistantMsgId, {
              status: "done",
              blocks: [
                {
                  kind: "text",
                  id: assistantBlockId,
                  content: finalReplyContent,
                  streaming: false,
                },
              ],
              hasDisclaimer: true,
            });

            if (hasFinishMarker || newRound >= MAX_COLLECT_ROUNDS) {
              setRightPanel(panelType);
              setPanelContent("");
              setGenerating(true);

              const generateReport = async () => {
                let reportSystemPrompt = "";
                if (chatAction === "prescription") {
                  reportSystemPrompt = role === "doctor"
                    ? "你是GerClaw老年科医生AI助手。请基于之前的对话信息，生成一份完整、专业、结构化的Markdown格式五大处方报告（药物处方、运动处方、营养处方、心理处方、康复处方），包含循证依据和注意事项。每个处方给出具体可执行的建议。报告末尾附上医疗免责声明。"
                    : "你是GerClaw老年科AI医生助手。请基于之前的对话信息，生成一份完整、亲切、易懂的Markdown格式五大处方报告（药物处方、运动处方、营养处方、心理处方、康复处方），用简单易懂的语言给出具体可执行的建议。报告末尾附上医疗免责声明。";
                } else {
                  reportSystemPrompt = role === "doctor"
                    ? `你是GerClaw老年科医生AI助手。请基于之前的对话信息，生成一份专业的Markdown格式用药审查报告。
报告必须以"⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。"开头。
报告结构：# 用药审查报告 ## 一、用药汇总 ## 二、潜在相互作用提示 ## 三、Beers标准提醒 ## 四、剂量建议 ## 五、就医建议。
报告末尾附上医疗免责声明。`
                    : `你是GerClaw老年科AI医生助手。请基于之前的对话信息，生成一份易懂的Markdown格式用药审查报告。
报告必须以"⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。"开头。
报告结构：# 用药审查报告 ## 一、您正在吃的药 ## 二、需要注意的问题 ## 三、老年人用药提醒 ## 四、给您的建议 ## 五、什么时候需要看医生。
报告末尾附上医疗免责声明。`;
                }

                const reportMessages: LLMMessage[] = [
                  { role: "system", content: reportSystemPrompt },
                ];
                
                for (const msg of recentMessages) {
                  if (msg.role === "user") {
                    reportMessages.push({ role: "user", content: getTextFromMessage(msg) });
                  } else if (msg.role === "assistant") {
                    const msgText = getTextFromMessage(msg);
                    if (msgText) {
                      reportMessages.push({ role: "assistant", content: msgText });
                    }
                  }
                }
                
                if (reportContent) {
                  reportMessages.push({ role: "assistant", content: reportContent });
                }
                reportMessages.push({ role: "user", content: "请生成完整报告。" });

                let isFirstChunk = true;
                let accumulatedReport = reportContent;
                
                abortControllerRef.current = new AbortController();
                
                streamChat(
                  reportMessages,
                  { signal: abortControllerRef.current.signal },
                  {
                    onText: (delta, fullText) => {
                      if (isFirstChunk) {
                        setPanelContent(fullText);
                        isFirstChunk = false;
                        accumulatedReport = fullText;
                      } else {
                        appendPanelContent(delta);
                        accumulatedReport += delta;
                      }
                    },
                    onDone: () => {
                      abortControllerRef.current = null;
                      const finalReport = postprocessMedicalText(accumulatedReport);
                      setPanelContent(finalReport);
                      
                      const summaryMsg: Message = {
                        id: generateId("msg"),
                        sessionId: sid,
                        role: "assistant",
                        blocks: [
                          {
                            kind: "text",
                            id: generateId("block"),
                            content: chatAction === "prescription"
                              ? (role === "doctor" ? "五大处方已生成，请在右侧面板查看。" : "您的五大处方建议已经生成好啦，请点击右侧面板查看完整内容哦～")
                              : (role === "doctor" ? "用药审查报告已生成，请在右侧面板查看。" : "您的用药审查结果已经生成好啦，请点击右侧面板查看完整内容哦～"),
                          },
                          {
                            kind: "action",
                            id: generateId("block"),
                            summary: chatAction === "prescription" ? "处方已生成" : "审查已完成",
                            buttonLabel,
                            panelType,
                          },
                        ],
                        status: "done",
                        createdAt: Date.now(),
                        hasDisclaimer: true,
                      };
                      addMessage(summaryMsg);
                      setGenerating(false);
                      setChatAction("none");
                    },
                    onError: () => {
                      abortControllerRef.current = null;
                      const fallbackReport = reportContent || (chatAction === "prescription" 
                        ? "# 五大处方建议\n\n## 一、药物处方\n请遵医嘱按时服药，注意观察用药反应。\n\n## 二、运动处方\n建议每天进行30分钟温和运动，如散步、太极拳。\n\n## 三、营养处方\n均衡饮食，多吃蔬菜水果，适量蛋白质。\n\n## 四、心理处方\n保持心情愉悦，多与家人朋友交流。\n\n## 五、康复处方\n根据身体状况循序渐进地进行康复训练。"
                        : "# 用药审查报告\n\n⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。\n\n## 一、用药汇总\n请核对您的用药清单。\n\n## 二、潜在相互作用提示\n建议咨询专业药师。\n\n## 三、老年人用药提醒\n注意用药剂量，避免多重用药。\n\n## 四、建议\n定期复查，遵医嘱调整用药。\n\n## 五、就医建议\n如有不适请及时就医。");
                      const finalReport = postprocessMedicalText(fallbackReport);
                      setPanelContent(finalReport);
                      
                      const summaryMsg: Message = {
                        id: generateId("msg"),
                        sessionId: sid,
                        role: "assistant",
                        blocks: [
                          {
                            kind: "text",
                            id: generateId("block"),
                            content: chatAction === "prescription"
                              ? "五大处方已生成，请在右侧面板查看。"
                              : "用药审查报告已生成，请在右侧面板查看。",
                          },
                          {
                            kind: "action",
                            id: generateId("block"),
                            summary: chatAction === "prescription" ? "处方已生成" : "审查已完成",
                            buttonLabel,
                            panelType,
                          },
                        ],
                        status: "done",
                        createdAt: Date.now(),
                        hasDisclaimer: true,
                      };
                      addMessage(summaryMsg);
                      setGenerating(false);
                      setChatAction("none");
                    },
                  }
                );
              };

              generateReport();
            } else {
              setGenerating(false);
            }
          },
          onError: (error) => {
            abortControllerRef.current = null;
            const errorContent = postprocessMedicalText(`抱歉，发生了错误：${error.message}`);
            updateMessage(assistantMsgId, {
              status: "error",
              blocks: [
                {
                  kind: "text",
                  id: assistantBlockId,
                  content: errorContent,
                  streaming: false,
                },
              ],
              hasDisclaimer: true,
            });
            setGenerating(false);
          },
        }
      );
      return;
    }

    const assistantMsgId = generateId("msg");
    const assistantBlockId = generateId("block");
    const searchBlockId = generateId("block");
    const needSearch = detectSearchNeed(text);

    const assistantMsg: Message = {
      id: assistantMsgId,
      sessionId: sid,
      role: "assistant",
      blocks: [
        {
          kind: "text",
          id: assistantBlockId,
          content: "",
          streaming: true,
        },
      ],
      status: "streaming",
      createdAt: Date.now(),
      hasDisclaimer: false,
    };
    addMessage(assistantMsg);

    const sessionMessages = messagesBySession[sid] ?? [];
    const recentMessages = sessionMessages.slice(-40);

    const buildLLMMessages = (searchContext: string): LLMMessage[] => {
      const llmMessages: LLMMessage[] = [];
      let systemPrompt = buildSystemPrompt(role);
      if (hasHighRisk) {
        systemPrompt += "\n\n重要提示：用户提到了高风险症状，你已经发送了紧急就医提示，请继续温和地安抚用户并强调立即就医的重要性，不要给出其他医疗建议。";
      }
      if (searchContext) {
        systemPrompt += searchContext;
      }
      llmMessages.push({ role: "system", content: systemPrompt });

      for (const msg of recentMessages) {
        if (msg.id === assistantMsgId) continue;
        if (msg.role === "user") {
          llmMessages.push({ role: "user", content: getTextFromMessage(msg) });
        } else if (msg.role === "assistant") {
          const msgText = getTextFromMessage(msg);
          if (msgText) {
            llmMessages.push({ role: "assistant", content: msgText });
          }
        }
      }
      return llmMessages;
    };

    const buildBlocksWithText = (
      textContent: string,
      isStreaming: boolean,
      searchResults?: SearchResultItem[]
    ): MessageBlock[] => {
      const blocks: MessageBlock[] = [];
      if (searchResults && searchResults.length > 0) {
        blocks.push({
          kind: "search_results",
          id: searchBlockId,
          data: searchResults,
        });
      }
      blocks.push({
        kind: "text",
        id: assistantBlockId,
        content: textContent,
        streaming: isStreaming,
      });
      return blocks;
    };

    const startStreaming = (searchResults: SearchResultItem[]) => {
      const searchContext = formatSearchResultsForLLM(searchResults);
      const llmMessages = buildLLMMessages(searchContext);

      if (searchResults.length > 0) {
        updateMessage(assistantMsgId, {
          blocks: buildBlocksWithText("", true, searchResults),
        });
      }

      abortControllerRef.current = new AbortController();

      streamChat(
        llmMessages,
        { signal: abortControllerRef.current.signal },
        {
          onText: (_delta, fullText) => {
            updateMessage(assistantMsgId, {
              blocks: buildBlocksWithText(fullText, true, searchResults.length > 0 ? searchResults : undefined),
            });
          },
          onDone: (fullText) => {
            abortControllerRef.current = null;
            const finalContent = postprocessMedicalText(fullText);
            updateMessage(assistantMsgId, {
              status: "done",
              blocks: buildBlocksWithText(finalContent, false, searchResults.length > 0 ? searchResults : undefined),
              hasDisclaimer: true,
            });
            setGenerating(false);

            if (!isRegenerate) {
              const sessionMsgs = messagesBySession[sid] ?? [];
              const firstUserMsg = sessionMsgs.find((m) => m.role === "user");
              if (firstUserMsg) {
                trySetSessionTitle(sid, getTextFromMessage(firstUserMsg));
              }
            }
          },
          onError: (error) => {
            abortControllerRef.current = null;
            const errorContent = postprocessMedicalText(`抱歉，发生了错误：${error.message}`);
            updateMessage(assistantMsgId, {
              status: "error",
              blocks: buildBlocksWithText(errorContent, false, searchResults.length > 0 ? searchResults : undefined),
              hasDisclaimer: true,
            });
            setGenerating(false);
          },
        }
      );
    };

    if (needSearch) {
      search(text)
        .then((results) => {
          startStreaming(results);
        })
        .catch(() => {
          startStreaming([]);
        });
    } else {
      startStreaming([]);
    }
  };

  const handleExampleClick = (text: string) => {
    handleSend(text);
  };

  const handleStartAction = (action: ChatActionType) => {
    // 从欢迎页启动功能：确保有会话 + 设置 chatAction
    if (!currentSessionId) {
      const sid = createSession(role);
      setCurrentSession(sid);
    }
    // 先关闭右侧面板
    const { closeRightPanel } = useAppStore.getState();
    closeRightPanel();
    setChatAction(action);
  };

  /** CGA：用户选择量表后，记录选择并初始化答题状态 */
  const handleSelectScale = (scale: Scale) => {
    if (!currentSessionId) return;
    setCgaSelectedScale((prev) => ({
      ...prev,
      [currentSessionId]: scale.id,
    }));
    setCgaCurrentIndex((prev) => ({ ...prev, [currentSessionId]: 0 }));
    setCgaAnswers((prev) => ({ ...prev, [currentSessionId]: {} }));
    setCgaCompleted((prev) => ({ ...prev, [currentSessionId]: false }));
  };

  /** 退出当前功能模式，清理相关状态（老年模式下二次确认）*/
  const handleExitAction = () => {
    // 老年模式下退出功能时二次确认，避免误操作丢失进度
    if (seniorMode && chatAction !== "none") {
      setShowExitConfirm(true);
      return;
    }
    doExitAction();
  };
  const doExitAction = () => {
    setShowExitConfirm(false);
    if (currentSessionId) {
      setCgaSelectedScale((prev) => {
        if (!prev[currentSessionId]) return prev;
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
      setCgaAnswers((prev) => {
        if (!prev[currentSessionId]) return prev;
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
      setCgaCurrentIndex((prev) => {
        if (prev[currentSessionId] === undefined) return prev;
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
      setCgaCompleted((prev) => {
        if (!prev[currentSessionId]) return prev;
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
      setCollectRounds((prev) => {
        if (prev[currentSessionId] === undefined) return prev;
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
    }
    actionInitRef.current = null;
    setChatAction("none");
  };

  /** CGA：重新选择量表（返回选量表界面，重置答题） */
  const handleReselectScale = () => {
    if (!currentSessionId) return;
    actionInitRef.current = null;
    setCgaSelectedScale((prev) => {
      const next = { ...prev };
      delete next[currentSessionId];
      return next;
    });
    setCgaAnswers((prev) => {
      const next = { ...prev };
      delete next[currentSessionId];
      return next;
    });
    setCgaCurrentIndex((prev) => {
      const next = { ...prev };
      delete next[currentSessionId];
      return next;
    });
    setCgaCompleted((prev) => {
      const next = { ...prev };
      delete next[currentSessionId];
      return next;
    });
  };

  /** CGA：选择某个选项后，记录答案（不自动跳转，需手动点"下一题"） */
  const handleAnswerQuestion = (question: ScaleQuestion, value: number) => {
    if (!currentSessionId) return;
    // 仅记录答案，高亮选中项，激活"下一题"按钮
    setCgaAnswers((prev) => ({
      ...prev,
      [currentSessionId]: {
        ...(prev[currentSessionId] ?? {}),
        [question.id]: value,
      },
    }));
  };

  /** CGA：跳到上一题 */
  const handlePrevQuestion = () => {
    if (!currentSessionId) return;
    setCgaCurrentIndex((prev) => ({
      ...prev,
      [currentSessionId]: Math.max(0, (prev[currentSessionId] ?? 0) - 1),
    }));
  };

  /** CGA：跳到下一题（需已回答当前题）；最后一题则完成评估 */
  const handleNextQuestion = () => {
    if (!currentSessionId || !selectedScaleObj) return;
    const idx = cgaCurrentIndex[currentSessionId] ?? 0;
    if (idx >= selectedScaleObj.questions.length - 1) {
      setCgaCompleted((prev) => ({ ...prev, [currentSessionId]: true }));
      
      // 计算得分并生成AI解读
      const answers = cgaAnswers[currentSessionId] ?? {};
      let totalScore = 0;
      const answerDetails: string[] = [];
      
      selectedScaleObj.questions.forEach((q) => {
        const answerValue = answers[q.id] as number | undefined;
        const score = answerValue ?? 0;
        totalScore += score;
        
        const selectedOption = q.options?.find((o) => o.value === score);
        answerDetails.push(
          `- ${q.text}\n  回答：${selectedOption?.label ?? "未作答"}（${score}分）`
        );
      });

      let level = "";
      let interpretation = "";
      for (const threshold of selectedScaleObj.grading.thresholds) {
        if (totalScore <= threshold.max) {
          level = threshold.level;
          interpretation = threshold.interpretation;
          break;
        }
      }

      const phq9SuicideRisk = !!(selectedScaleObj.id === "scale_phq9" && (answers["phq9_9"] as number | undefined) && (answers["phq9_9"] as number) > 0);

      setRightPanel("cga");
      setPanelContent("");
      setGenerating(true);

      const cgaSystemPrompt = role === "doctor"
        ? `你是GerClaw老年科医生AI助手，正在解读${selectedScaleObj.fullName}（${selectedScaleObj.name}）评估结果。
请基于患者的答题结果，给出专业的评估解读：
1. 得分与分级说明
2. 各维度/题目分析
3. 针对性的临床建议
4. 随访建议
${phq9SuicideRisk ? "⚠️ 重要：PHQ-9第9题（自杀意念）得分>0，必须强烈建议立即就医评估，并给出心理危机干预热线：全国心理危机干预热线 400-161-9995，北京心理危机研究与干预中心 010-82951332。" : ""}
请用Markdown格式输出，结构清晰，包含循证依据参考。报告末尾附上医疗免责声明。`
        : `你是GerClaw老年科AI医生助手，正在为老年患者解读${selectedScaleObj.fullName}（${selectedScaleObj.name}）评估结果。
请用亲切、易懂的语言为老人解释评估结果：
1. 您的得分情况说明
2. 各项回答的分析（用简单的话讲）
3. 给您的具体建议
4. 什么时候需要看医生
${phq9SuicideRisk ? "⚠️ 重要：您在最后一题提到了伤害自己的想法，请务必立即告诉家人或医生，也可以拨打心理危机干预热线：400-161-9995（全国）或 010-82951332（北京），会有人24小时帮助您。" : ""}
请用Markdown格式输出，语言温暖、易懂，避免专业术语。报告末尾附上医疗免责声明。`;

      const cgaPromptText = `量表名称：${selectedScaleObj.fullName}（${selectedScaleObj.name}）
总分：${totalScore} 分
分级：${level}（${interpretation}）

各题回答详情：
${answerDetails.join("\n")}

请基于以上信息生成完整的评估解读报告。`;

      const cgaMessages: LLMMessage[] = [
        { role: "system", content: cgaSystemPrompt },
        { role: "user", content: cgaPromptText },
      ];

      abortControllerRef.current = new AbortController();

      streamChat(
        cgaMessages,
        { signal: abortControllerRef.current.signal },
        {
          onText: (delta, fullText) => {
            setPanelContent(fullText);
          },
          onDone: (fullText) => {
            abortControllerRef.current = null;
            const finalReport = postprocessMedicalText(fullText, { isSuicideRisk: phq9SuicideRisk });
            setPanelContent(finalReport);
            setGenerating(false);
          },
          onError: () => {
            abortControllerRef.current = null;
            const fallbackReport = `# ${selectedScaleObj.fullName}评估结果

## 得分情况
- 总分：**${totalScore} 分**
- 分级：**${level}**
- ${interpretation}

## 各题回答
${answerDetails.join("\n")}

## 建议
${phq9SuicideRisk 
  ? "⚠️ **重要提示**：您在评估中提到了伤害自己的想法，请立即告诉家人或医生，或拨打心理危机干预热线：\n- 全国心理危机干预热线：400-161-9995\n- 北京心理危机研究与干预中心：010-82951332"
  : level.includes("重度") || level.includes("障碍")
    ? "建议您尽快就医，寻求专业医生的帮助。"
    : level.includes("中度")
      ? "建议您关注相关症状，必要时咨询专业医生。"
      : "您的评估结果基本正常，建议保持健康的生活方式，定期复查。"
}

${MEDICAL_DISCLAIMER}`;
            setPanelContent(postprocessMedicalText(fallbackReport));
            setGenerating(false);
          },
        }
      );
      
      return;
    }
    setCgaCurrentIndex((prev) => ({
      ...prev,
      [currentSessionId]: idx + 1,
    }));
  };

  /** 判断当前 CGA 是否处于"选量表"阶段 */
  const showScaleSelector =
    chatAction === "cga" &&
    !!currentSessionId &&
    !cgaSelectedScale[currentSessionId];

  /** 判断当前 CGA 是否处于"答题"阶段 */
  const showCgaQuiz =
    chatAction === "cga" &&
    !!currentSessionId &&
    !!cgaSelectedScale[currentSessionId] &&
    !cgaCompleted[currentSessionId];

  /** CGA 答题完成 */
  const cgaFinished =
    chatAction === "cga" &&
    !!currentSessionId &&
    !!cgaCompleted[currentSessionId];

  const selectedScaleObj =
    chatAction === "cga" && currentSessionId
      ? scales.find((s) => s.id === cgaSelectedScale[currentSessionId])
      : null;

  // CGA 答题：当前题目
  const currentQuestion: ScaleQuestion | null =
    showCgaQuiz && selectedScaleObj
      ? selectedScaleObj.questions[
          cgaCurrentIndex[currentSessionId!] ?? 0
        ] ?? null
      : null;

  // CGA 答题：当前会话已答的题
  const currentAnswers = currentSessionId
    ? cgaAnswers[currentSessionId] ?? {}
    : {};

  const actionTitles: Record<string, string> = {
    prescription: "五大处方生成",
    cga: "老年综合评估",
    "drug-review": "用药审查",
    "health-profile": "查看健康画像",
  };

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-background">
      {/* 粘性头部 — 功能模式下始终显示功能标题栏 */}
      {(chatAction !== "none" || (currentSessionId && messages.length > 0)) && (
        <header
          className="sticky top-0 z-10 flex items-center justify-between px-4 h-12 border-b border-border bg-background/95 backdrop-blur"
          style={sidebarCollapsed ? { paddingLeft: "112px" } : undefined}
        >
          {showScaleSelector ? (
            <>
              <span className="font-medium">老年综合评估 — 选择量表</span>
              <button
                type="button"
                onClick={handleExitAction}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                退出
              </button>
            </>
          ) : chatAction !== "none" ? (
            <>
              <span className="font-medium">
                {actionTitles[chatAction]}
                {chatAction === "cga" && selectedScaleObj && (
                  <span className="text-muted-foreground font-normal ml-2">
                    · {selectedScaleObj.fullName}
                  </span>
                )}
              </span>
              <button
                type="button"
                onClick={handleExitAction}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                退出
              </button>
            </>
          ) : (
            <span
              className="font-medium truncate"
              title={currentSessionTitle}
            >
              {currentSessionTitle || "新对话"}
            </span>
          )}
        </header>
      )}

      {messages.length === 0 && chatAction === "none" ? (
        <WelcomePage
          onExampleClick={handleExampleClick}
          onStartAction={handleStartAction}
          role={role}
          seniorMode={seniorMode}
        />
      ) : showScaleSelector ? (
        /* CGA 选量表阶段：中间栏展示量表选择卡片 */
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-4 py-8">
            <div className="mb-6">
              <h2 className="text-lg font-semibold mb-1">老年综合评估（CGA）</h2>
              <p className="text-sm text-muted-foreground">
                {role === "doctor"
                  ? "请选择本次需要进行的评估量表。选择后将逐题作答。"
                  : "您好，请选择您想做的评估，选好后我会通过几个简单的问题来帮您评估。"}
              </p>
            </div>
            <ScaleSelector scales={scales} onSelect={handleSelectScale} />
            <div className="mt-6 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              AI 评估仅供健康参考，不能替代医生诊断。身体不适请及时就医。
            </div>
          </div>
        </div>
      ) : showCgaQuiz && currentQuestion && selectedScaleObj ? (
        /* CGA 答题阶段：逐题展示题目 + 选项卡片 */
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-4 py-6">
            {/* 进度条（老年模式辅助文字≥18px） */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <span className={cn("text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                  第 {(cgaCurrentIndex[currentSessionId!] ?? 0) + 1} / {selectedScaleObj.questions.length} 题
                </span>
                <span className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-xs")}>
                  {selectedScaleObj.fullName}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full bg-primary transition-all"
                  style={{
                    width: `${(((cgaCurrentIndex[currentSessionId!] ?? 0) + 1) / selectedScaleObj.questions.length) * 100}%`,
                  }}
                />
              </div>
            </div>

            {/* 题目（老年模式≥18px） */}
            <div className="mb-6">
              <h3 className={cn("font-semibold mb-1", seniorMode ? "text-xl" : "text-lg")}>
                {currentQuestion.text}
              </h3>
              {currentQuestion.hint && (
                <p className={cn("text-muted-foreground mt-1", seniorMode ? "text-base" : "text-sm")}>
                  {currentQuestion.hint}
                </p>
              )}
            </div>

            {/* 选项卡片（老年模式间距≥16px） */}
            <div className={cn(seniorMode ? "space-y-4" : "space-y-2.5")}>
              {currentQuestion.options?.map((opt) => {
                const selected = currentAnswers[currentQuestion.id] === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => handleAnswerQuestion(currentQuestion, opt.value)}
                    className={cn(
                      "w-full flex items-start gap-3 rounded-lg border p-4 text-left transition-all",
                      seniorMode && "p-5",
                      selected
                        ? "border-primary bg-primary/10 ring-1 ring-primary"
                        : "border-border bg-card hover:border-primary/40 hover:bg-muted/40"
                    )}
                  >
                    <div
                      className={cn(
                        "flex items-center justify-center size-7 rounded-full border-2 shrink-0 mt-0.5",
                        seniorMode && "size-9",
                        selected
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-muted-foreground/30"
                      )}
                    >
                      {selected && <CheckCircle2 className="size-4" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className={cn("font-medium", seniorMode ? "text-lg" : "text-base")}>
                        {opt.label}
                      </div>
                      {opt.description && (
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {opt.description}
                        </div>
                      )}
                    </div>
                    {opt.value > 0 && (
                      <span className="text-xs text-muted-foreground shrink-0">
                        {opt.value} 分
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* 上一题 / 下一题（适老化大按钮，选中后激活） */}
            <div className="flex items-center justify-between mt-8 gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePrevQuestion}
                disabled={(cgaCurrentIndex[currentSessionId!] ?? 0) === 0}
                className={cn("shrink-0", seniorMode && "min-h-12 px-5 text-base")}
                aria-label="上一题"
              >
                ← 上一题
              </Button>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleReselectScale}
                  className={cn(
                    "text-sm text-muted-foreground hover:text-foreground",
                    seniorMode && "text-base"
                  )}
                >
                  重选量表
                </button>
                {currentAnswers[currentQuestion.id] !== undefined && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={handleNextQuestion}
                    className={cn(
                      "shrink-0",
                      seniorMode && "min-h-12 px-6 text-base"
                    )}
                    aria-label={
                      (cgaCurrentIndex[currentSessionId!] ?? 0) >=
                      selectedScaleObj.questions.length - 1
                        ? "提交评估"
                        : "下一题"
                    }
                  >
                    {(cgaCurrentIndex[currentSessionId!] ?? 0) >=
                    selectedScaleObj.questions.length - 1
                      ? "提交评估 →"
                      : "下一题 →"}
                  </Button>
                )}
              </div>
            </div>

            <div className="mt-8 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              AI 评估仅供健康参考，不能替代医生诊断。身体不适请及时就医。
            </div>
          </div>
        </div>
      ) : cgaFinished && selectedScaleObj ? (
        /* CGA 答题完成 */
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-4 py-12 text-center">
            <div className="flex justify-center mb-4">
              <div className="flex items-center justify-center size-16 rounded-full bg-primary/10 text-primary">
                <CheckCircle2 className="size-8" />
              </div>
            </div>
            <h2 className={cn("font-semibold mb-2", seniorMode ? "text-2xl" : "text-xl")}>
              评估完成
            </h2>
            <p className={cn("text-muted-foreground mb-6", seniorMode ? "text-lg" : "text-base")}>
              {selectedScaleObj.fullName} 已完成，评估结果已生成。
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={handleReselectScale}
                className={cn(
                  "px-4 py-2 rounded-md border border-border text-sm hover:bg-muted",
                  seniorMode && "text-base py-3 px-6"
                )}
              >
                重新评估
              </button>
              <button
                type="button"
                onClick={() => setRightPanel("cga")}
                className={cn(
                  "px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90",
                  seniorMode && "text-base py-3 px-6"
                )}
              >
                查看评估报告 →
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto">
          {messages.length > 0 && <MessageList messages={messages} onRegenerate={handleRegenerate} />}

          {/* 功能模式：AI 正在生成时的加载提示 */}
          {chatAction !== "none" && isGenerating && (
            <div className="px-4 py-2 max-w-3xl mx-auto">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                AI 正在分析…
              </div>
            </div>
          )}
        </div>
      )}

      {/* CGA 选量表/答题/完成阶段隐藏对话输入框 */}
      {!showScaleSelector && !showCgaQuiz && !cgaFinished && (
        <ChatInput
          onSend={handleSend}
          isGenerating={isGenerating}
          onStop={handleStop}
        />
      )}

      {/* 老年模式：退出功能二次确认弹窗 */}
      <Dialog open={showExitConfirm} onOpenChange={setShowExitConfirm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-5 text-amber-500" />
              确认退出？
            </DialogTitle>
          </DialogHeader>
          <p className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-sm")}>
            退出后当前进度将不会保存，确定要退出吗？
          </p>
          <DialogFooter className="gap-2">
            <DialogClose render={<Button variant="outline">取消</Button>} />
            <Button variant="destructive" onClick={doExitAction}>
              确认退出
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
