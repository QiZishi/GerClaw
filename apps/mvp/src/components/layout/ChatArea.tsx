"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ArrowLeft,
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
import { CGAConversation } from "@/components/cga/CGAConversation";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { scales } from "@/data/scales";
import { cn } from "@/lib/utils";
import { HIGH_RISK_SYMPTOMS, EMERGENCY_ALERT } from "@/lib/constants";
import { postprocessMedicalText } from "@/lib/security-postprocess";
import { desensitizeForLLM } from "@/lib/security";
import { streamChat, buildSystemPrompt, type LLMMessage } from "@/services/llm";
import { generateId } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { retrieveKnowledge } from "@/services/knowledge/client";
import type { ChatActionType, Citation, ImageAttachment, Message, MessageBlock, SearchResultItem, Scale, ScaleResult } from "@/types";

/** 检测文本中是否包含高风险症状关键词（铁律5关联） */
function detectHighRiskSymptoms(text: string): string[] {
  const matched: string[] = [];
  for (const kw of HIGH_RISK_SYMPTOMS) {
    if (text.includes(kw)) matched.push(kw);
  }
  return matched;
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

/** 获取功能的开场消息（患者端 vs 医生端 vs 访客端不同话术）*/
function getOpeningMessage(
  action: ChatActionType,
  role: "patient" | "doctor" | "visitor",
  scaleName?: string
): string {
  if (role === "visitor") {
    return "欢迎体验 GerClaw！请先在左下角菜单选择「患者模式」或「医生模式」开始使用完整功能。您也可以直接提问了解平台功能。";
  }
  const isPatient = role === "patient";
  switch (action) {
    case "prescription":
      return "欢迎使用五大处方生成系统，请描述您的健康情况或上传相关资料...";
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
  const selectedModelId = useChatStore((s) => s.selectedModelId);
  const { stop: stopTTS } = useAudioPlayer();

  const messagesBySession = useChatStore((s) => s.messagesBySession);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const appendMessageText = useChatStore((s) => s.appendMessageText);
  const initMessageThinking = useChatStore((s) => s.initMessageThinking);
  const startMessageThinkingBlock = useChatStore((s) => s.startMessageThinkingBlock);
  const appendMessageThinking = useChatStore((s) => s.appendMessageThinking);
  const finalizeMessageThinking = useChatStore((s) => s.finalizeMessageThinking);
  const initMessageToolCall = useChatStore((s) => s.initMessageToolCall);
  const completeMessageToolCall = useChatStore((s) => s.completeMessageToolCall);
  const removeMessage = useChatStore((s) => s.removeMessage);
  const updateSession = useChatStore((s) => s.updateSession);
  const createSession = useChatStore((s) => s.createSession);
  const storeSessions = useChatStore((s) => s.sessions);

  const abortControllerRef = useRef<AbortController | null>(null);
  const currentThinkingBlockIdRef = useRef<string | null>(null);

  // 各会话功能模式下的对话轮次计数（sessionId -> count），上限5轮
  const [collectRounds, setCollectRounds] = useState<Record<string, number>>({});
  const MAX_COLLECT_ROUNDS = 5;
  const actionInitRef = useRef<string | null>(null);

  // 五大处方模式：已收集的患者基本信息（sessionId -> Record<key, {label, value}>）
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_prescriptionCollectedInfo, setPrescriptionCollectedInfo] = useState<
    Record<string, Record<string, { label: string; value?: string }>>
  >({});

  /** 从对话文本中提取患者基本信息（年龄/性别/慢病/用药/吸烟/饮酒/运动/饮食/睡眠/情绪） */
  const extractPatientInfoFromText = useCallback((text: string): Record<string, { label: string; value?: string }> => {
    const result: Record<string, { label: string; value?: string }> = {};

    const ageMatch = text.match(/([0-9]{1,3})\s*岁/);
    if (ageMatch) {
      result.age = { label: "年龄", value: `${ageMatch[1]}岁` };
    }

    const genderMatch = text.match(/(男|女|男性|女性)/);
    if (genderMatch) {
      const gender = genderMatch[1];
      result.gender = {
        label: "性别",
        value: gender.includes("男") ? "男" : "女",
      };
    }

    const chronicDiseasePatterns = [
      /(?:有|患|得|患有|得有|有.*?病史|慢病|慢性病|基础病)[：:是为]?\s*([^，。,\.\n]{2,50})/,
      /(?:高血压|糖尿病|冠心病|心脏病|脑卒中|中风|慢阻肺|关节炎|骨质疏松|痴呆|前列腺增生|白内障|青光眼)/g,
    ];
    let chronicDiseases: string[] = [];
    for (const pattern of chronicDiseasePatterns) {
      const matches = text.match(pattern);
      if (matches) {
        chronicDiseases = [...chronicDiseases, ...matches.map(m => m.replace(/^(有|患|得|患有|得有)/, "").trim())];
      }
    }
    const knownDiseases = ["高血压", "糖尿病", "冠心病", "心脏病", "脑卒中", "中风", "慢阻肺", "关节炎", "骨质疏松", "痴呆", "前列腺增生", "白内障", "青光眼"];
    const foundKnown = knownDiseases.filter(d => text.includes(d));
    chronicDiseases = [...new Set([...chronicDiseases, ...foundKnown])];
    if (chronicDiseases.length > 0) {
      result.chronic_diseases = { label: "慢性疾病", value: chronicDiseases.join("、") };
    }

    const medicationPatterns = [
      /(?:吃药|服药|用药|在吃|正在吃|吃.*?药|服用)[：:是为]?\s*([^，。,\.\n]{2,80})/,
      /(?:阿司匹林|二甲双胍|氨氯地平|硝苯地平|美托洛尔|阿托伐他汀|瑞舒伐他汀|氯吡格雷|奥美拉唑|左氧氟沙星|头孢|布洛芬)/g,
    ];
    let medications: string[] = [];
    for (const pattern of medicationPatterns) {
      const matches = text.match(pattern);
      if (matches) {
        medications = [...medications, ...matches.map(m => m.trim())];
      }
    }
    const knownMeds = ["阿司匹林", "二甲双胍", "氨氯地平", "硝苯地平", "美托洛尔", "阿托伐他汀", "瑞舒伐他汀", "氯吡格雷", "奥美拉唑", "左氧氟沙星", "头孢", "布洛芬"];
    const foundKnownMeds = knownMeds.filter(d => text.includes(d));
    medications = [...new Set([...medications, ...foundKnownMeds])];
    if (medications.length > 0) {
      result.medications = { label: "当前用药", value: medications.join("、") };
    }

    const smokingMatch = text.match(/(抽烟|吸烟|不抽烟|不吸烟|戒烟|已戒烟|烟龄)/);
    if (smokingMatch) {
      let smokeStatus = "";
      if (text.includes("不抽烟") || text.includes("不吸烟") || text.includes("戒烟") || text.includes("已戒烟")) {
        smokeStatus = text.includes("戒烟") || text.includes("已戒烟") ? "已戒烟" : "不吸烟";
      } else {
        smokeStatus = "吸烟";
      }
      result.smoking = { label: "吸烟情况", value: smokeStatus };
    }

    const alcoholMatch = text.match(/(喝酒|饮酒|不喝酒|不饮酒|戒酒|已戒酒|酒龄|白酒|啤酒|红酒)/);
    if (alcoholMatch) {
      let alcoholStatus = "";
      if (text.includes("不喝酒") || text.includes("不饮酒") || text.includes("戒酒") || text.includes("已戒酒")) {
        alcoholStatus = text.includes("戒酒") || text.includes("已戒酒") ? "已戒酒" : "不饮酒";
      } else {
        alcoholStatus = "饮酒";
      }
      result.alcohol = { label: "饮酒情况", value: alcoholStatus };
    }

    const exerciseMatch = text.match(/(运动|锻炼|散步|跑步|太极|广场舞|健身|活动)/);
    if (exerciseMatch) {
      let exerciseStatus = "";
      if (text.includes("不运动") || text.includes("不锻炼") || text.includes("很少运动") || text.includes("几乎不运动")) {
        exerciseStatus = "缺乏运动";
      } else if (text.includes("每天") || text.includes("经常") || text.includes("规律")) {
        exerciseStatus = "规律运动";
      } else {
        exerciseStatus = text.match(/(?:运动|锻炼)[：:是为]?\s*([^，。,\.\n]{2,30})/)?.[1] || "有活动";
      }
      result.exercise = { label: "运动情况", value: exerciseStatus };
    }

    const dietMatch = text.match(/(饮食|吃饭|胃口|吃素|吃荤|咸|淡|甜|油腻|清淡)/);
    if (dietMatch) {
      let dietStatus = "";
      if (text.includes("清淡")) dietStatus = "饮食清淡";
      else if (text.includes("咸") || text.includes("重口味")) dietStatus = "口味偏咸";
      else if (text.includes("甜") || text.includes("吃糖")) dietStatus = "喜食甜食";
      else if (text.includes("油腻")) dietStatus = "饮食油腻";
      else if (text.includes("素")) dietStatus = "偏素食";
      else dietStatus = text.match(/(?:饮食|吃饭)[：:是为]?\s*([^，。,\.\n]{2,30})/)?.[1] || "一般";
      result.diet = { label: "饮食情况", value: dietStatus };
    }

    const sleepMatch = text.match(/(睡觉|睡眠|失眠|入睡|多梦|早醒|睡不好|睡得好|睡眠质量)/);
    if (sleepMatch) {
      let sleepStatus = "";
      if (text.includes("失眠") || text.includes("睡不好") || text.includes("入睡困难") || text.includes("多梦") || text.includes("早醒")) {
        sleepStatus = "睡眠不佳";
      } else if (text.includes("睡得好") || text.includes("睡眠好")) {
        sleepStatus = "睡眠良好";
      } else {
        sleepStatus = text.match(/(?:睡觉|睡眠)[：:是为]?\s*([^，。,\.\n]{2,30})/)?.[1] || "一般";
      }
      result.sleep = { label: "睡眠情况", value: sleepStatus };
    }

    const moodPatterns = [/(心情|情绪|开心|高兴|难过|焦虑|抑郁|烦躁|低落|压力|孤独|郁闷)/];
    for (const pattern of moodPatterns) {
      const match = text.match(pattern);
      if (match) {
        let moodStatus = "";
        if (text.includes("焦虑") || text.includes("抑郁") || text.includes("烦躁") || text.includes("低落") || text.includes("孤独") || text.includes("郁闷") || text.includes("难过")) {
          moodStatus = "情绪欠佳";
        } else if (text.includes("开心") || text.includes("高兴") || text.includes("心情好")) {
          moodStatus = "情绪良好";
        } else {
          moodStatus = match[1] || "一般";
        }
        result.mood = { label: "情绪状态", value: moodStatus };
        break;
      }
    }

    return result;
  }, []);

  /** 向AI消息添加或更新信息收集卡片block */
  const addOrUpdateInfoBlock = useCallback((sessionId: string, assistantMsgId: string, fields: Array<{key:string;label:string;value?:string;filled:boolean}>) => {
    const currentMsgs = useChatStore.getState().messagesBySession[sessionId] ?? [];
    const msg = currentMsgs.find(m => m.id === assistantMsgId);
    if (!msg) return;

    const existingBlock = msg.blocks.find(b => b.kind === "info_collection");
    const newBlock: MessageBlock = {
      kind: "info_collection",
      id: existingBlock?.id ?? generateId("block"),
      data: { fields },
    };

    let newBlocks: MessageBlock[];
    if (existingBlock) {
      newBlocks = msg.blocks.map(b => b.kind === "info_collection" ? newBlock : b);
    } else {
      const lastTextBlockIdx = msg.blocks.findIndex(b => b.kind === "text");
      if (lastTextBlockIdx !== -1) {
        newBlocks = [
          ...msg.blocks.slice(0, lastTextBlockIdx + 1),
          newBlock,
          ...msg.blocks.slice(lastTextBlockIdx + 1),
        ];
      } else {
        newBlocks = [...msg.blocks, newBlock];
      }
    }

    updateMessage(assistantMsgId, { blocks: newBlocks });
  }, [updateMessage]);

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // CGA：当前会话已选择的评估量表ID列表（sessionId -> string[]）
  const [cgaSelectedScales, setCgaSelectedScales] = useState<
    Record<string, string[]>
  >({});
  // CGA：已完成的量表结果（sessionId -> ScaleResult[]）
  const [cgaResults, setCgaResults] = useState<
    Record<string, ScaleResult[]>
  >({});
  // CGA：是否处于答题阶段（sessionId -> boolean）
  const [cgaShowQuiz, setCgaShowQuiz] = useState<Record<string, boolean>>({});
  // 老年模式退出功能二次确认弹窗
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const [exitConfirmType, setExitConfirmType] = useState<'default' | 'cga-in-progress' | 'cga-has-result'>('default');



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

    if (chatAction === "health-profile" && role === "patient") {
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

    // prescription 和 drug-review 使用固定欢迎语（不经过LLM）
    if (chatAction === "prescription" || chatAction === "drug-review") {
      const initKey = `${sid}:${chatAction}`;
      if (actionInitRef.current === initKey) return;
      actionInitRef.current = initKey;
      
      setGenerating(true);
      setPanelContent("");
      
      setTimeout(() => {
        setCollectRounds((prev) => ({ ...prev, [sid!]: 0 }));
        const openingContent = postprocessMedicalText(getOpeningMessage(chatAction, role));
        const initialFields: Array<{key:string;label:string;value?:string;filled:boolean}> = chatAction === "prescription"
          ? [
              { key: "age", label: "年龄", filled: false },
              { key: "gender", label: "性别", filled: false },
              { key: "chronic_diseases", label: "慢性疾病", filled: false },
              { key: "medications", label: "当前用药", filled: false },
              { key: "smoking", label: "吸烟情况", filled: false },
              { key: "alcohol", label: "饮酒情况", filled: false },
              { key: "exercise", label: "运动情况", filled: false },
              { key: "diet", label: "饮食情况", filled: false },
              { key: "sleep", label: "睡眠情况", filled: false },
              { key: "mood", label: "情绪状态", filled: false },
            ]
          : [];
        const aiMsg: Message = {
          id: generateId("msg"),
          sessionId: sid!,
          role: "assistant",
          blocks: [
            {
              kind: "text",
              id: generateId("block"),
              content: openingContent,
            },
            ...(initialFields.length > 0 ? [{
              kind: "info_collection" as const,
              id: generateId("block"),
              data: { fields: initialFields },
            }] : []),
          ],
          status: "done",
          createdAt: Date.now(),
          hasDisclaimer: true,
        };
        addMessage(aiMsg);
        setGenerating(false);
      }, 100);
      return;
    }

    const initKey = `${sid}:${chatAction}`;
    if (actionInitRef.current === initKey) return;
    actionInitRef.current = initKey;

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
  }, [chatAction, currentSessionId, role, createSession, setCurrentSession, addMessage, setGenerating, setPanelContent, updateMessage, appendMessageText, appendPanelContent, initMessageThinking, startMessageThinkingBlock, appendMessageThinking, finalizeMessageThinking]);

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
    const currentMsgs = currentSessionId ? useChatStore.getState().messagesBySession[currentSessionId] ?? [] : [];
    const streamingMsg = currentMsgs.find((m) => m.status === "streaming");
    if (streamingMsg) {
      streamingMsg.blocks.forEach((b) => {
        if (b.kind === "thinking" && b.data.status === "thinking") {
          finalizeMessageThinking(streamingMsg.id, b.id);
        }
      });
      const existingTextBlock = streamingMsg.blocks.find(b => b.kind === "text") as { content: string } | undefined;
      const existingContent = existingTextBlock?.content || "";
      const blocks = streamingMsg.blocks.map((b) => {
        if (b.kind === "text") {
          return { ...b, streaming: false, content: existingContent };
        }
        return b;
      });
      updateMessage(streamingMsg.id, {
        status: "done",
        blocks,
        hasDisclaimer: true,
      });
    }
    setGenerating(false);
    useAppStore.getState().setStreamingInterrupted(false);
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
    const userImages: ImageAttachment[] = userMsg.blocks
      .filter((b): b is Extract<MessageBlock, { kind: "image" }> => b.kind === "image")
      .map((b) => b.data);
    
    const messagesToRemove = messages.slice(userMsgIndex + 1, aiMsgIndex + 1);
    messagesToRemove.forEach((m) => removeMessage(m.id));
    
    doSend(currentSessionId, userText, true, userImages.length > 0 ? userImages : undefined);
  };

  const handleSend = (text: string, images?: ImageAttachment[]) => {
    if (!currentSessionId) {
      const sid = createSession(role);
      setCurrentSession(sid);
      setTimeout(() => doSend(sid, text, false, images), 50);
      return;
    }
    doSend(currentSessionId, text, false, images);
  };

  const handleFileParsed = (fileName: string, markdown: string) => {
    const fileMessage = `📄 **文件解析结果：${fileName}**\n\n<file-parsed>\n${markdown}\n</file-parsed>\n\n请根据以上文件内容回答我的问题。`;
    if (!currentSessionId) {
      const sid = createSession(role);
      setCurrentSession(sid);
      setTimeout(() => doSend(sid, fileMessage, false), 50);
      return;
    }
    doSend(currentSessionId, fileMessage, false);
  };

  const doSend = (sid: string, text: string, isRegenerate = false, images?: ImageAttachment[]) => {
    const userBlocks: MessageBlock[] = [];
    if (images && images.length > 0) {
      for (const img of images) {
        userBlocks.push({
          kind: "image",
          id: generateId("block"),
          data: img,
        });
      }
    }
    if (text) {
      userBlocks.push({ kind: "text", id: generateId("block"), content: text });
    }
    const userMsg: Message = {
      id: generateId("msg"),
      sessionId: sid,
      role: "user",
      blocks: userBlocks,
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

    // 从store获取最新的消息（避免闭包陈旧值问题）
    const getLatestMessages = (): Message[] => {
      return useChatStore.getState().messagesBySession[sid] ?? [];
    };

    const messageBlocksToLLMContent = (msg: Message): string | LLMMessage["content"] => {
      const textParts: string[] = [];
      const imageParts: { type: "image_url"; image_url: { url: string } }[] = [];
      for (const block of msg.blocks) {
        if (block.kind === "text") {
          textParts.push(desensitizeForLLM(block.content));
        } else if (block.kind === "image") {
          const { mimeType, base64 } = block.data;
          imageParts.push({
            type: "image_url",
            image_url: { url: `data:${mimeType};base64,${base64}` },
          });
        }
      }
      const textContent = textParts.join("\n").trim();
      if (imageParts.length === 0) {
        return textContent;
      }
      const parts: LLMMessage["content"] = [];
      if (textContent) {
        parts.push({ type: "text", text: textContent });
      }
      parts.push(...imageParts);
      return parts.length > 0 ? parts : textContent;
    };

    const buildLLMHistory = (excludeMsgId?: string): LLMMessage[] => {
      const allMsgs = getLatestMessages();
      const result: LLMMessage[] = [];
      for (const m of allMsgs) {
        if (m.id === excludeMsgId) continue;
        if (m.role !== "user" && m.role !== "assistant") continue;
        const content = messageBlocksToLLMContent(m);
        if (content === null) continue;
        const isEmpty = typeof content === "string" ? !content : content.length === 0;
        if (m.role === "assistant" && isEmpty) continue;
        if (isEmpty) continue;
        result.push({ role: m.role, content });
      }
      return result;
    };

    if (chatAction !== "none" && chatAction !== "cga") {
      const newRound = (collectRounds[sid] ?? 0) + 1;
      setCollectRounds((prev) => ({ ...prev, [sid]: newRound }));

      const assistantMsgId = generateId("msg");
      const assistantBlockId = generateId("block");
      const initialThinkingBlockId = generateId("block");
      currentThinkingBlockIdRef.current = initialThinkingBlockId;

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
      initMessageThinking(assistantMsgId, initialThinkingBlockId);

      const forceGenerate = newRound >= MAX_COLLECT_ROUNDS;

      const buildActionMessages = (): LLMMessage[] => {
        const llmMessages: LLMMessage[] = [];

        let systemPrompt = "";

        if (chatAction === "prescription") {
          systemPrompt = role === "doctor"
            ? `你是GerClaw老年科医生AI助手，正在协助医生生成五大处方（运动处方、营养处方、心理处方、用药处方、戒烟限酒处方）。请通过对话收集患者信息，一次只问1-2个关键问题。
需要收集的信息包括：年龄、性别、慢性疾病、当前用药、吸烟情况、饮酒情况、运动情况、饮食情况、睡眠情况、情绪状态。
当你认为收集到足够信息后，或对话达到5轮时，在回复末尾输出特殊标记 [生成处方]。
${forceGenerate ? "重要：已达到对话轮次上限，请立即输出 [生成处方] 标记。" : ""}`
            : `你是GerClaw老年科AI医生助手，正在为老年患者生成五大处方（运动处方、营养处方、心理处方、用药处方、戒烟限酒处方）。请通过亲切自然的对话了解患者情况，像聊天一样一次只问1-2个问题。
需要了解的信息包括：年龄、性别、有什么慢性病、正在吃什么药、是否抽烟喝酒、平时运动吗、吃饭怎么样、睡眠好不好、心情怎么样。
当你觉得了解得差不多了，或者聊了5轮之后，在回复末尾输出特殊标记 [生成处方]。
${forceGenerate ? "重要：已经聊了足够多啦，请立即输出 [生成处方] 标记，我来为您生成处方。" : ""}`;
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

        // 使用getLatestMessages获取包含刚添加消息的最新历史
        const history = buildLLMHistory(assistantMsgId);
        llmMessages.push(...history);

        return llmMessages;
      };

      const finishMarker = chatAction === "prescription" ? "[生成处方]" : "[生成审查]";
      const panelType = chatAction as "prescription" | "drug-review";
      const buttonLabel = chatAction === "prescription" ? "查看完整处方" : "查看审查结果";

      abortControllerRef.current = new AbortController();

      streamChat(
        buildActionMessages(),
        { signal: abortControllerRef.current.signal, tools: [], modelPreference: selectedModelId },
        {
          onThinkingStart: () => {
            const newBlockId = generateId("block");
            currentThinkingBlockIdRef.current = newBlockId;
            startMessageThinkingBlock(assistantMsgId, newBlockId);
          },
          onThinkingDelta: (delta) => {
            const currentId = currentThinkingBlockIdRef.current;
            if (currentId) {
              appendMessageThinking(assistantMsgId, currentId, delta);
            }
          },
          onThinkingDone: () => {
            const currentId = currentThinkingBlockIdRef.current;
            if (currentId) {
              finalizeMessageThinking(assistantMsgId, currentId);
            }
          },
          onText: (delta) => {
            appendMessageText(assistantMsgId, assistantBlockId, delta);
          },
          onFallback: (message) => {
            toast.show(message);
          },
          onDone: (fullText) => {
            abortControllerRef.current = null;
            const currentId = currentThinkingBlockIdRef.current;
            if (currentId) {
              finalizeMessageThinking(assistantMsgId, currentId);
            }
            
            const hasFinishMarker = fullText.includes(finishMarker);
            let replyText = fullText;
            let reportContent = "";
            
            if (hasFinishMarker) {
              const parts = fullText.split(finishMarker);
              replyText = parts[0].trim();
              reportContent = parts.slice(1).join(finishMarker).trim();
            }

            const finalReplyContent = postprocessMedicalText(replyText);
            const currentMsg = useChatStore.getState().messagesBySession[sid]?.find(m => m.id === assistantMsgId);
            const updatedBlocks = currentMsg?.blocks.map((b) => {
              if (b.kind === "text" && b.id === assistantBlockId) {
                return { ...b, content: finalReplyContent, streaming: false };
              }
              return b;
            }) ?? [];
            updateMessage(assistantMsgId, {
              status: "done",
              blocks: updatedBlocks,
              hasDisclaimer: true,
            });

            if (chatAction === "prescription") {
              const allMsgs = getLatestMessages();
              const allText = allMsgs
                .filter(m => m.role === "user" || m.role === "assistant")
                .map(m => m.blocks.filter(b => b.kind === "text").map(b => (b as {content: string}).content).join("\n"))
                .join("\n");

              const newInfo = extractPatientInfoFromText(allText);
              setPrescriptionCollectedInfo(prev => {
                const updated = { ...prev[sid], ...newInfo };
                const fields: Array<{key:string;label:string;value?:string;filled:boolean}> = [
                  { key: "age", label: "年龄", value: updated.age?.value, filled: !!updated.age },
                  { key: "gender", label: "性别", value: updated.gender?.value, filled: !!updated.gender },
                  { key: "chronic_diseases", label: "慢性疾病", value: updated.chronic_diseases?.value, filled: !!updated.chronic_diseases },
                  { key: "medications", label: "当前用药", value: updated.medications?.value, filled: !!updated.medications },
                  { key: "smoking", label: "吸烟情况", value: updated.smoking?.value, filled: !!updated.smoking },
                  { key: "alcohol", label: "饮酒情况", value: updated.alcohol?.value, filled: !!updated.alcohol },
                  { key: "exercise", label: "运动情况", value: updated.exercise?.value, filled: !!updated.exercise },
                  { key: "diet", label: "饮食情况", value: updated.diet?.value, filled: !!updated.diet },
                  { key: "sleep", label: "睡眠情况", value: updated.sleep?.value, filled: !!updated.sleep },
                  { key: "mood", label: "情绪状态", value: updated.mood?.value, filled: !!updated.mood },
                ];
                addOrUpdateInfoBlock(sid, assistantMsgId, fields);
                return { ...prev, [sid]: updated };
              });
            }

            if (hasFinishMarker || newRound >= MAX_COLLECT_ROUNDS) {
              setPanelContent("");
              setGenerating(true);

              const generateReport = async () => {
                let reportSystemPrompt = "";
                if (chatAction === "prescription") {
                  reportSystemPrompt = role === "doctor"
                    ? `你是GerClaw老年科医生AI助手。请基于之前的对话信息，生成一份完整、专业、结构化的Markdown格式五大处方报告。
报告结构必须严格按照以下顺序：
# 老年综合评估五大处方建议

## 一、运动处方
（具体运动类型、强度、频率、时长、注意事项，适合老年人的运动如散步、太极拳等）

## 二、营养处方
（饮食原则、营养建议、食谱示例、注意事项，考虑老年人生理特点）

## 三、心理处方
（心理状态评估、干预措施、社会支持建议、转诊建议）

## 四、用药处方
（当前用药整理、潜在相互作用风险、高风险用药警告、用药建议、注意事项，如有高风险用药请用⚠️标注）

## 五、戒烟限酒处方
（吸烟饮酒情况评估、戒烟限酒建议、具体方法）

## ⚠️ 重要提示
如果发现以下高风险情况，请在此处明确提示立即就医：
- 胸痛、胸闷、呼吸困难
- 突发肢体无力、言语不清
- 严重头晕、意识障碍
- 药物严重不良反应
- 自杀倾向或严重抑郁

要求：
1. 每个处方给出具体可执行的建议，包含循证依据
2. 用药处方必须检查潜在药物相互作用
3. 所有建议必须适合老年人
4. 不要在报告中添加免责声明，系统会自动添加`
                    : `你是GerClaw老年科AI医生助手。请基于之前的对话信息，用简单易懂的语言生成一份亲切的Markdown格式五大处方报告。
报告结构必须严格按照以下顺序：
# 给您的五大处方建议

## 一、运动处方
（告诉您适合做什么运动、做多久、注意什么，比如散步、打太极都很好）

## 二、营养处方
（告诉您吃什么好、怎么吃更健康，饭要吃好，营养要够）

## 三、心理处方
（告诉您怎么保持好心情，多和家人朋友聊聊天，心情不好要告诉家人或医生）

## 四、用药处方
（帮您整理现在吃的药，告诉您吃药要注意什么，如果有风险会用⚠️提醒您）

## 五、戒烟限酒处方
（告诉您抽烟喝酒的危害，帮您慢慢戒掉）

## ⚠️ 重要提醒
如果有这些不舒服，请马上告诉家人并去医院：
- 胸口疼、闷得慌、喘不上气
- 突然手脚没力气、说话不清楚
- 头晕得厉害、甚至不清醒
- 吃药后很难受
- 心里特别难受、不想活了

要求：
1. 说的话要简单好懂，像家里人跟您说话一样
2. 每个建议都要具体，能直接照着做
3. 吃药的事一定要说清楚注意什么
4. 不要在报告里加"免责声明"这些字，系统会自动加`;
                } else {
                  reportSystemPrompt = role === "doctor"
                    ? `你是GerClaw老年科医生AI助手。请基于之前的对话信息，生成一份专业的Markdown格式用药审查报告。
报告必须以"⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。"开头。
报告结构：# 用药审查报告 ## 一、用药汇总 ## 二、潜在相互作用提示 ## 三、Beers标准提醒 ## 四、剂量建议 ## 五、就医建议。
不要在报告末尾额外添加免责声明。`
                    : `你是GerClaw老年科AI医生助手。请基于之前的对话信息，生成一份易懂的Markdown格式用药审查报告。
报告必须以"⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。"开头。
报告结构：# 用药审查报告 ## 一、您正在吃的药 ## 二、需要注意的问题 ## 三、老年人用药提醒 ## 四、给您的建议 ## 五、什么时候需要看医生。
不要在报告末尾额外添加免责声明。`;
                }

                const reportMessages: LLMMessage[] = [
                  { role: "system", content: reportSystemPrompt },
                ];

                // 使用最新的对话历史
                const historyForReport = buildLLMHistory(assistantMsgId);
                reportMessages.push(...historyForReport);

                if (reportContent) {
                  reportMessages.push({ role: "assistant", content: reportContent });
                }
                reportMessages.push({ role: "user", content: "请基于以上对话信息生成完整报告。" });

                let isFirstChunk = true;
                let accumulatedReport = reportContent;
                
                abortControllerRef.current = new AbortController();
                
                streamChat(
                  reportMessages,
                  { signal: abortControllerRef.current.signal, tools: [], modelPreference: selectedModelId },
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
                    onFallback: (message) => {
                      toast.show(message);
                    },
                    onDone: () => {
                      abortControllerRef.current = null;
                      const MEDICAL_DISCLAIMER = "\n\n---\n\n⚠️ **免责声明**：本处方由AI系统生成，仅供健康参考，不能替代专业医生的诊断和治疗建议。如有不适，请及时就医，遵医嘱调整用药和治疗方案。如出现胸痛、呼吸困难、突发肢体无力等紧急情况，请立即拨打120急救电话。";
                      let finalReport = postprocessMedicalText(accumulatedReport);
                      if (chatAction === "prescription" && !finalReport.includes("免责声明")) {
                        finalReport += MEDICAL_DISCLAIMER;
                      }
                      setPanelContent(finalReport);
                      setRightPanel(panelType);
                      
                      const summaryText = chatAction === "prescription"
                        ? (role === "doctor" ? "五大处方已生成，请在右侧面板查看。" : "您的五大处方建议已经生成好啦，请点击右侧面板查看完整内容哦～")
                        : (role === "doctor" ? "用药审查报告已生成，请在右侧面板查看。" : "您的用药审查结果已经生成好啦，请点击右侧面板查看完整内容哦～");
                      const summaryMsg: Message = {
                        id: generateId("msg"),
                        sessionId: sid,
                        role: "assistant",
                        blocks: [
                          {
                            kind: "text",
                            id: generateId("block"),
                            content: summaryText,
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
                      const MEDICAL_DISCLAIMER = "\n\n---\n\n⚠️ **免责声明**：本处方由AI系统生成，仅供健康参考，不能替代专业医生的诊断和治疗建议。如有不适，请及时就医。";
                      const fallbackReport = reportContent || (chatAction === "prescription" 
                        ? `# 老年综合评估五大处方建议\n\n## 一、运动处方\n建议每天进行30分钟温和运动，如散步、太极拳，循序渐进，避免剧烈运动。运动时如有不适请立即停止。\n\n## 二、营养处方\n均衡饮食，多吃蔬菜水果，适量优质蛋白质（如鱼、蛋、豆制品），少盐少油少糖，饮食清淡易消化。\n\n## 三、心理处方\n保持心情愉悦，多与家人朋友交流，积极参与社区活动。如持续情绪低落，请及时咨询心理医生。\n\n## 四、用药处方\n请遵医嘱按时服药，不要自行增减药量或停药。注意观察用药反应，如有不适及时咨询医生或药师。\n\n## 五、戒烟限酒处方\n建议戒烟，限制饮酒。如戒烟困难可咨询医生获取专业帮助。\n\n## ⚠️ 重要提示\n如有胸痛、呼吸困难、突发肢体无力等紧急情况，请立即拨打120就医。${MEDICAL_DISCLAIMER}`
                        : "# 用药审查报告\n\n⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。\n\n## 一、用药汇总\n请核对您的用药清单。\n\n## 二、潜在相互作用提示\n建议咨询专业药师。\n\n## 三、老年人用药提醒\n注意用药剂量，避免多重用药。\n\n## 四、建议\n定期复查，遵医嘱调整用药。\n\n## 五、就医建议\n如有不适请及时就医。");
                      let finalReport = postprocessMedicalText(fallbackReport);
                      if (chatAction === "prescription" && !finalReport.includes("免责声明")) {
                        finalReport += MEDICAL_DISCLAIMER;
                      }
                      setPanelContent(finalReport);
                      setRightPanel(panelType);
                      
                      const summaryText = chatAction === "prescription"
                        ? "五大处方已生成，请在右侧面板查看。"
                        : "用药审查报告已生成，请在右侧面板查看。";
                      const summaryMsg: Message = {
                        id: generateId("msg"),
                        sessionId: sid,
                        role: "assistant",
                        blocks: [
                          {
                            kind: "text",
                            id: generateId("block"),
                            content: summaryText,
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
          onError: () => {
            abortControllerRef.current = null;
            const currentId = currentThinkingBlockIdRef.current;
            if (currentId) {
              finalizeMessageThinking(assistantMsgId, currentId);
            }
            const currentMsg = useChatStore.getState().messagesBySession[sid]?.find(m => m.id === assistantMsgId);
            const existingTextBlock = currentMsg?.blocks.find(b => b.kind === "text" && b.id === assistantBlockId);
            const existingContent = existingTextBlock && existingTextBlock.kind === "text" ? existingTextBlock.content : "";
            
            let finalContent = existingContent;
            if (!finalContent.trim()) {
              finalContent = "抱歉，生成过程中出现问题，请重新发送消息或点击重新生成。";
            }
            const processedContent = postprocessMedicalText(finalContent);
            
            const updatedBlocks = currentMsg?.blocks.map((b) => {
              if (b.kind === "text" && b.id === assistantBlockId) {
                return { ...b, content: processedContent, streaming: false };
              }
              return b;
            }) ?? [];
            updateMessage(assistantMsgId, {
              status: "done",
              blocks: updatedBlocks,
              hasDisclaimer: true,
            });
            setGenerating(false);
            useAppStore.getState().setStreamingInterrupted(false);
          },
        }
      );
      return;
    }

    const assistantMsgId = generateId("msg");
    const assistantBlockId = generateId("block");
    const initialThinkingBlockId = generateId("block");
    currentThinkingBlockIdRef.current = initialThinkingBlockId;

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
    initMessageThinking(assistantMsgId, initialThinkingBlockId);

    const toolCallBlockMap = new Map<string, string>();
    let allCitations: Citation[] = [];

    const buildLLMMessages = (kbContext?: string): LLMMessage[] => {
      const llmMessages: LLMMessage[] = [];
      let systemPrompt = buildSystemPrompt(role);
      if (hasHighRisk) {
        systemPrompt += "\n\n重要提示：用户提到了高风险症状，你已经发送了紧急就医提示，请继续温和地安抚用户并强调立即就医的重要性，不要给出其他医疗建议。";
      }
      if (kbContext) {
        systemPrompt += `\n\n【本地知识库参考资料】\n以下是从本地老年医学知识库中检索到的与用户问题相关的内容，请参考这些专业资料来回答用户问题，但不要在回复中提及"知识库"或"检索"等词汇，自然地整合这些信息：\n${kbContext}`;
      }
      llmMessages.push({ role: "system", content: systemPrompt });

      const history = buildLLMHistory(assistantMsgId);
      llmMessages.push(...history);
      return llmMessages;
    };

    const doStreamChat = async () => {
      let kbContext = "";
      try {
        const kbResult = await retrieveKnowledge(text, 3);
        if (kbResult.success && kbResult.chunks.length > 0) {
          kbContext = kbResult.chunks
            .map((chunk, i) => `[参考${i + 1}] ${chunk.title}（${chunk.category}）\n${chunk.content}`)
            .join("\n\n");
        }
      } catch {
      }

      const llmMessages = buildLLMMessages(kbContext);

      abortControllerRef.current = new AbortController();

      streamChat(
      llmMessages,
      { signal: abortControllerRef.current.signal, modelPreference: selectedModelId },
      {
        onThinkingStart: () => {
          const newBlockId = generateId("block");
          currentThinkingBlockIdRef.current = newBlockId;
          startMessageThinkingBlock(assistantMsgId, newBlockId);
        },
        onThinkingDelta: (delta) => {
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId) {
            appendMessageThinking(assistantMsgId, currentId, delta);
          }
        },
        onThinkingDone: () => {
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId) {
            finalizeMessageThinking(assistantMsgId, currentId);
          }
        },
        onText: (delta) => {
          appendMessageText(assistantMsgId, assistantBlockId, delta);
        },
        onFallback: (message) => {
          toast.show(message);
        },
        onToolCallStart: ({ id, name }) => {
          const toolBlockId = generateId("block");
          toolCallBlockMap.set(id, toolBlockId);
          initMessageToolCall(assistantMsgId, toolBlockId, id, name);
        },
        onToolCallDelta: () => {
        },
        onToolCallEnd: (toolCallId, args) => {
          const toolBlockId = toolCallBlockMap.get(toolCallId);
          if (!toolBlockId) return;
          const currentMsg = useChatStore.getState().messagesBySession[sid]?.find(m => m.id === assistantMsgId);
          if (!currentMsg) return;
          const toolBlock = currentMsg.blocks.find(b => b.kind === "tool_call" && b.id === toolBlockId);
          if (toolBlock && toolBlock.kind === "tool_call") {
            updateMessage(assistantMsgId, {
              blocks: currentMsg.blocks.map(b => {
                if (b.kind === "tool_call" && b.id === toolBlockId) {
                  return {
                    ...b,
                    data: { ...b.data, args },
                  };
                }
                return b;
              }),
            });
          }
        },
        onToolResult: (toolCallId, result) => {
          const toolBlockId = toolCallBlockMap.get(toolCallId);
          if (!toolBlockId) return;

          const currentMsg = useChatStore.getState().messagesBySession[sid]?.find(m => m.id === assistantMsgId);
          if (!currentMsg) return;

          const toolBlock = currentMsg.blocks.find(b => b.kind === "tool_call" && b.id === toolBlockId);
          let args: Record<string, unknown> = {};
          if (toolBlock && toolBlock.kind === "tool_call") {
            args = toolBlock.data.args || {};
          }

          completeMessageToolCall(assistantMsgId, toolBlockId, args, result);

          if (toolBlock && toolBlock.kind === "tool_call" && toolBlock.data.toolName === "web_search") {
            const searchData = result as { results?: { title: string; url: string; content: string; source?: string; published_date?: string }[] };
            const results = searchData.results || [];
            if (results.length > 0) {
              const searchResults: SearchResultItem[] = results.map((r) => {
                let source = "";
                try {
                  const url = new URL(r.url);
                  source = url.hostname.replace(/^www\./, "");
                } catch {
                  source = r.url;
                }
                return {
                  id: generateId("search"),
                  title: r.title || "无标题",
                  url: r.url,
                  source: r.source || source,
                  snippet: r.content || "",
                  publishedDate: r.published_date,
                };
              });

              const newCitations: Citation[] = searchResults.map((r, i) => ({
                id: allCitations.length + i + 1,
                title: r.title,
                snippet: r.snippet,
                url: r.url,
                source: r.source,
                publishedDate: r.publishedDate,
              }));
              allCitations = [...allCitations, ...newCitations];

              updateMessage(assistantMsgId, {
                citations: allCitations.length > 0 ? allCitations : undefined,
              });
            }
          }
        },
        onDone: (fullText) => {
          abortControllerRef.current = null;
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId) {
            finalizeMessageThinking(assistantMsgId, currentId);
          }
          const finalContent = postprocessMedicalText(fullText);
          const msgNow = useChatStore.getState().messagesBySession[sid]?.find(m => m.id === assistantMsgId);
          const updatedBlocks = msgNow?.blocks.map((b) => {
            if (b.kind === "text" && b.id === assistantBlockId) {
              return { ...b, content: finalContent, streaming: false };
            }
            return b;
          }) ?? [];
          updateMessage(assistantMsgId, {
            status: "done",
            blocks: updatedBlocks,
            citations: allCitations.length > 0 ? allCitations : undefined,
            hasDisclaimer: true,
          });
          setGenerating(false);

          if (!isRegenerate) {
            const latestMsgs = useChatStore.getState().messagesBySession[sid] ?? [];
            const firstUserMsg = latestMsgs.find((m) => m.role === "user");
            if (firstUserMsg) {
              trySetSessionTitle(sid, getTextFromMessage(firstUserMsg));
            }
          }
        },
        onError: () => {
          abortControllerRef.current = null;
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId) {
            finalizeMessageThinking(assistantMsgId, currentId);
          }
          const msgNow = useChatStore.getState().messagesBySession[sid]?.find(m => m.id === assistantMsgId);
          const existingTextBlock = msgNow?.blocks.find(b => b.kind === "text" && b.id === assistantBlockId);
          const existingContent = existingTextBlock && existingTextBlock.kind === "text" ? existingTextBlock.content : "";

          let finalContent = existingContent;
          if (!finalContent.trim()) {
            finalContent = "抱歉，生成过程中出现问题，请重新发送消息或点击重新生成。";
          }
          const processedContent = postprocessMedicalText(finalContent);

          const updatedBlocks = msgNow?.blocks.map((b) => {
            if (b.kind === "text" && b.id === assistantBlockId) {
              return { ...b, content: processedContent, streaming: false };
            }
            return b;
          }) ?? [];
          updateMessage(assistantMsgId, {
            status: "done",
            blocks: updatedBlocks,
            hasDisclaimer: true,
          });
          setGenerating(false);
          useAppStore.getState().setStreamingInterrupted(false);
        },
      }
    );
  };

  doStreamChat();
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

  // CGA多选：当前选择的量表ID
  const [cgaTempSelectedIds, setCgaTempSelectedIds] = useState<string[]>([]);
  const [cgaActiveScales, setCgaActiveScales] = useState<Scale[]>([]);

  const cgaSessionSelectedIds = useMemo(
    () => currentSessionId ? cgaSelectedScales[currentSessionId] ?? [] : [],
    [currentSessionId, cgaSelectedScales]
  );
  const cgaSessionResults = useMemo(
    () => currentSessionId ? cgaResults[currentSessionId] ?? [] : [],
    [currentSessionId, cgaResults]
  );
  const cgaSessionShowQuiz = useMemo(
    () => currentSessionId ? cgaShowQuiz[currentSessionId] ?? false : false,
    [currentSessionId, cgaShowQuiz]
  );
  const cgaCompletedScaleIds = useMemo(
    () => cgaSessionResults.map(r => r.scaleId),
    [cgaSessionResults]
  );

  const cgaInitialAnswers = useMemo(() => {
    const record: Record<string, number | string> = {};
    for (const r of cgaSessionResults) {
      if (!cgaSessionSelectedIds.includes(r.scaleId)) continue;
      Object.assign(record, r.answers);
    }
    return record;
  }, [cgaSessionResults, cgaSessionSelectedIds]);

  const showScaleSelector = chatAction === "cga" && !!currentSessionId && !cgaSessionShowQuiz;
  const showCgaQuiz = chatAction === "cga" && !!currentSessionId && cgaSessionShowQuiz && cgaActiveScales.length > 0;

  const handleCgaStartQuiz = () => {
    if (!currentSessionId || cgaTempSelectedIds.length === 0) return;
    const existing = cgaSelectedScales[currentSessionId] ?? [];
    const merged = Array.from(new Set([...existing, ...cgaTempSelectedIds]));
    setCgaSelectedScales(prev => ({ ...prev, [currentSessionId]: merged }));
    const activeScales = scales.filter(s => cgaTempSelectedIds.includes(s.id));
    setCgaActiveScales(activeScales);
    setCgaShowQuiz(prev => ({ ...prev, [currentSessionId]: true }));
  };

  const handleCgaComplete = (results: ScaleResult[]) => {
    if (!currentSessionId) return;
    setCgaResults(prev => {
      const existing = prev[currentSessionId] ?? [];
      const existingIds = new Set(existing.map(r => r.scaleId));
      const merged = [...existing];
      for (const r of results) {
        if (!existingIds.has(r.scaleId)) {
          merged.push(r);
        } else {
          const idx = merged.findIndex(x => x.scaleId === r.scaleId);
          if (idx >= 0) merged[idx] = r;
        }
      }
      return { ...prev, [currentSessionId]: merged };
    });
  };

  const handleCgaContinue = () => {
    if (!currentSessionId) return;
    setCgaShowQuiz(prev => ({ ...prev, [currentSessionId]: false }));
    setCgaTempSelectedIds([]);
    setCgaActiveScales([]);
  };

  const generateCGAReport = useCallback((scaleResults: ScaleResult[]) => {
    if (!currentSessionId) return;
    setPanelContent("");
    setGenerating(true);

    const resultsText = scaleResults.map(r => {
      const scale = scales.find(s => s.id === r.scaleId);
      const answerDetails = Object.entries(r.answers).map(([qId, val]) => {
        const question = scale?.questions.find(q => q.id === qId);
        const opt = question?.options?.find(o => o.value === val);
        return `- ${question?.text ?? qId}: ${opt?.label ?? val}（${val}分）`;
      }).join("\n");
      return `## ${r.scaleName}\n- 总分：${r.totalScore}/${r.maxScore}\n- 分级：${r.level}（${r.interpretation}）\n- 详细回答：\n${answerDetails}`;
    }).join("\n\n");

    const hasSuicideRisk = scaleResults.some(r => {
      const phq9Answer = r.answers["phq9_9"];
      return phq9Answer !== undefined && typeof phq9Answer === "number" && phq9Answer > 0;
    });

    const systemPrompt = role === "doctor"
      ? `你是GerClaw老年科医生AI助手，正在综合解读CGA老年综合评估结果。请基于以下量表结果，给出专业的综合评估解读：
1. 各量表得分与分级说明
2. 综合健康状况分析
3. 针对性的临床建议
4. 随访建议
${hasSuicideRisk ? "⚠️ 重要：PHQ-9第9题（自杀意念）得分>0，必须强烈建议立即就医评估，并给出心理危机干预热线：全国心理危机干预热线 400-161-9995，北京心理危机研究与干预中心 010-82951332。" : ""}
请用Markdown格式输出，结构清晰。不要在报告末尾添加免责声明，系统会自动显示。`
      : `你是GerClaw老年科AI医生助手，正在为老年患者解读CGA老年综合评估结果。
请用亲切、易懂的语言解释评估结果：
1. 您的各项得分情况
2. 整体健康状况分析（简单的话讲）
3. 给您的具体建议
4. 什么时候需要看医生
${hasSuicideRisk ? "⚠️ 重要：您在评估中提到了伤害自己的想法，请务必立即告诉家人或医生，也可以拨打心理危机干预热线：400-161-9995（全国）或 010-82951332（北京），会有人24小时帮助您。" : ""}
请用Markdown格式输出，语言温暖易懂。不要在报告末尾添加免责声明，系统会自动显示。`;

    const promptText = `# CGA老年综合评估结果\n\n${resultsText}\n\n请基于以上结果生成综合评估报告。`;

    const messages: LLMMessage[] = [
      { role: "system", content: systemPrompt },
      { role: "user", content: promptText },
    ];

    abortControllerRef.current = new AbortController();

    streamChat(
      messages,
      { signal: abortControllerRef.current.signal, tools: [], modelPreference: selectedModelId },
      {
        onText: (delta, fullText) => {
          setPanelContent(fullText);
        },
        onFallback: (message) => {
          toast.show(message);
        },
        onDone: (fullText) => {
          abortControllerRef.current = null;
          const finalReport = postprocessMedicalText(fullText, { isSuicideRisk: hasSuicideRisk });
          setPanelContent(finalReport);
          setRightPanel("cga");
          setGenerating(false);
        },
        onError: () => {
          abortControllerRef.current = null;
          const fallbackReport = `# CGA老年综合评估报告\n\n${resultsText}\n\n## 建议\n${hasSuicideRisk
            ? "⚠️ **重要提示**：您在评估中提到了伤害自己的想法，请立即告诉家人或医生，或拨打心理危机干预热线：\n- 全国心理危机干预热线：400-161-9995\n- 北京心理危机研究与干预中心：010-82951332"
            : "建议您携带评估结果咨询专业医生，获取个性化建议。"}`;
          setPanelContent(postprocessMedicalText(fallbackReport));
          setRightPanel("cga");
          setGenerating(false);
        },
      }
    );
  }, [currentSessionId, role, selectedModelId, setGenerating, setPanelContent, setRightPanel]);

  const handleCgaGenerateReport = () => {
    const results = currentSessionId ? cgaResults[currentSessionId] ?? [] : [];
    if (results.length > 0) {
      generateCGAReport(results);
    }
    if (currentSessionId) {
      setCgaShowQuiz(prev => ({ ...prev, [currentSessionId]: false }));
      setCgaTempSelectedIds([]);
      setCgaActiveScales([]);
    }
  };

  /** 退出当前功能模式，清理相关状态（老年模式下二次确认）*/
  const handleExitAction = () => {
    if (chatAction === "cga" && currentSessionId) {
      const hasResults = (cgaResults[currentSessionId] ?? []).length > 0;
      const hasProgress = cgaSessionShowQuiz;
      if (hasResults) {
        setExitConfirmType('cga-has-result');
        setShowExitConfirm(true);
        return;
      } else if (hasProgress) {
        setExitConfirmType('cga-in-progress');
        setShowExitConfirm(true);
        return;
      }
      doExitAction();
      return;
    }
    if (seniorMode && chatAction !== "none") {
      setExitConfirmType('default');
      setShowExitConfirm(true);
      return;
    }
    doExitAction();
  };
  const doExitAction = () => {
    setShowExitConfirm(false);
    stopTTS();
    if (currentSessionId) {
      setCgaSelectedScales(prev => {
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
      setCgaResults(prev => {
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
      setCgaShowQuiz(prev => {
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
      setCgaTempSelectedIds([]);
      setCgaActiveScales([]);
      setCollectRounds((prev) => {
        const next = { ...prev };
        delete next[currentSessionId];
        return next;
      });
    }
    actionInitRef.current = null;
    setChatAction("none");
  };

  const actionTitles: Record<string, string> = {
    prescription: "五大处方生成",
    cga: "老年综合评估",
    "drug-review": "用药审查",
    "health-profile": "查看健康画像",
  };

  if (!mounted) {
    return (
      <main className="flex-1 flex flex-col min-w-0 bg-background">
        <WelcomePage
          onExampleClick={() => {}}
          onStartAction={() => {}}
          role="visitor"
          seniorMode={false}
        />
      </main>
    );
  }

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

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-background">
      {/* 粘性头部 — 功能模式下始终显示功能标题栏 */}
      {(chatAction !== "none" || (currentSessionId && messages.length > 0)) && (
        <header
          className="sticky top-0 z-10 flex items-center justify-between px-4 h-12 border-b border-border bg-background/95 backdrop-blur"
          style={sidebarCollapsed ? { paddingLeft: "112px" } : undefined}
        >
          {chatAction !== "none" ? (
            <>
              <span className="font-medium">
                {actionTitles[chatAction]}
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
            <>
              <span
                className="font-medium truncate"
                title={currentSessionTitle}
              >
                {currentSessionTitle || "新对话"}
              </span>
            </>
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
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-4 py-8">
            <div className="mb-6">
              <h2 className={cn("font-semibold mb-1", seniorMode ? "text-xl" : "text-lg")}>
                老年综合评估（CGA）
              </h2>
              <p className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-sm")}>
                {role === "doctor"
                  ? "请选择本次需要进行的评估量表，支持多选。已完成的量表将不可再次选择。"
                  : "您好，请选择您想做的评估（可多选），选好后我会通过几个简单的问题来帮您评估。"}
              </p>
            </div>
            <ScaleSelector
              scales={scales}
              selectedScaleIds={cgaTempSelectedIds}
              completedScaleIds={cgaCompletedScaleIds}
              onSelectionChange={setCgaTempSelectedIds}
              onStart={handleCgaStartQuiz}
              onGenerateReport={handleCgaGenerateReport}
            />
            <div className={cn("mt-6 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30 px-3 py-2 text-amber-800 dark:text-amber-200", seniorMode ? "text-sm" : "text-xs")}>
              AI 评估仅供健康参考，不能替代医生诊断。身体不适请及时就医。
            </div>
          </div>
        </div>
      ) : showCgaQuiz ? (
        <CGAConversation
          scales={cgaActiveScales}
          initialAnswers={cgaInitialAnswers}
          onComplete={handleCgaComplete}
          onContinue={handleCgaContinue}
          onGenerateReport={handleCgaGenerateReport}
          onExit={doExitAction}
        />
      ) : (
        <div className="flex-1 min-h-0 flex flex-col">
          {messages.length > 0 && <MessageList messages={messages} onRegenerate={handleRegenerate} />}
        </div>
      )}

      {chatAction === "none" && (
        <ChatInput
          onSend={handleSend}
          isGenerating={isGenerating}
          onStop={handleStop}
          onFileParsed={handleFileParsed}
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
            {exitConfirmType === 'cga-has-result'
              ? "您已完成量表评估，退出后评估结果将丢失，确认退出吗？"
              : exitConfirmType === 'cga-in-progress'
                ? "退出后当前答题进度将不会保存，确认退出吗？"
                : "退出后当前进度将不会保存，确定要退出吗？"}
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
