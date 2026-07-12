"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CGA_PROGRESS_KEY = "gerclaw-cga-progress";

type CGAProgressData = {
  selectedScale?: string;
  answers?: Record<string, number | number[]>;
  currentIndex?: number;
  completed?: boolean;
};
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Mic,
  Volume2,
  VolumeX,
  X,
  Check,
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
import { HIGH_RISK_SYMPTOMS, EMERGENCY_ALERT } from "@/lib/constants";
import { postprocessMedicalText } from "@/lib/security-postprocess";
import { desensitizeForLLM } from "@/lib/security";
import { streamChat, buildSystemPrompt, type LLMMessage } from "@/services/llm";
import { generateId } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { recognizeAudio } from "@/services/voice/asr";
import type { ChatActionType, Citation, ImageAttachment, Message, MessageBlock, Scale, ScaleQuestion, SearchResultItem } from "@/types";

/** 检测文本中是否包含高风险症状关键词（铁律5关联） */
function detectHighRiskSymptoms(text: string): string[] {
  const matched: string[] = [];
  for (const kw of HIGH_RISK_SYMPTOMS) {
    if (text.includes(kw)) matched.push(kw);
  }
  return matched;
}

const POSITIVE_KEYWORDS = ["是", "是的", "对", "有", "嗯", "好", "没错", "正确", "对的", "嗯对", "有的"];
const NEGATIVE_KEYWORDS = ["否", "不是", "没有", "不", "无", "不对", "错", "不是的", "没", "木有"];
const NUMBER_MAP: Record<string, number> = {
  "1": 1, "一": 1, "第一个": 1, "第一": 1,
  "2": 2, "二": 2, "第二个": 2, "第二": 2,
  "3": 3, "三": 3, "第三个": 3, "第三": 3,
  "4": 4, "四": 4, "第四个": 4, "第四": 4,
  "5": 5, "五": 5, "第五个": 5, "第五": 5,
  "6": 6, "六": 6, "第六个": 6, "第六": 6,
};

function matchCGAAnswerByVoice(text: string, options: ScaleQuestion["options"]): number | null {
  if (!options) return null;
  const normalized = text.trim().replace(/[。，！？\s]/g, "");

  for (const keyword of POSITIVE_KEYWORDS) {
    if (normalized.includes(keyword)) {
      const yesOpt = options.find((o) => {
        const label = o.label.replace(/[。，！？\s]/g, "");
        return label.includes("是") || label === "是" || o.value === 1 || label.includes("有");
      });
      if (yesOpt) return yesOpt.value;
      if (options.length >= 2) return options[0].value;
    }
  }

  for (const keyword of NEGATIVE_KEYWORDS) {
    if (normalized.includes(keyword) && !normalized.includes("不是没有") && !normalized.includes("不是不")) {
      const noOpt = options.find((o) => {
        const label = o.label.replace(/[。，！？\s]/g, "");
        return label.includes("否") || label === "否" || label === "不是" || o.value === 0 || label.includes("没有") || label.includes("无");
      });
      if (noOpt) return noOpt.value;
      if (options.length >= 2) return options[options.length - 1].value;
    }
  }

  for (const [numStr, numVal] of Object.entries(NUMBER_MAP)) {
    if (normalized.includes(numStr) && numVal <= options.length) {
      const idx = numVal - 1;
      if (idx >= 0 && idx < options.length) return options[idx].value;
    }
  }

  for (const opt of options) {
    const label = opt.label.replace(/[。，！？\s]/g, "");
    if (label && (normalized.includes(label) || label.includes(normalized))) {
      return opt.value;
    }
  }

  return null;
}

function formatRecordingDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function WaveformBars({ audioLevel, recordingDuration, seniorMode }: { audioLevel: number; recordingDuration: number; seniorMode: boolean }) {
  const barCount = seniorMode ? 20 : 28;
  return (
    <div className="flex items-center justify-center gap-[3px] flex-1 px-4 overflow-hidden">
      {Array.from({ length: barCount }).map((_, i) => {
        const centerDist = Math.abs(i - barCount / 2) / (barCount / 2);
        const baseHeight = 4 + (1 - centerDist) * (seniorMode ? 10 : 8);
        const levelMultiplier = 0.4 + audioLevel * 1.8;
        const height = Math.min(baseHeight * levelMultiplier, seniorMode ? 36 : 28);
        const isActive = audioLevel > 0.05 || (i % 3 === 0 && recordingDuration % 2 === 0);
        return (
          <div
            key={i}
            className={cn(
              "w-[3px] rounded-full transition-all duration-100",
              isActive ? "bg-gray-800 dark:bg-gray-200" : "bg-gray-300 dark:bg-gray-600"
            )}
            style={{ height: `${height}px` }}
          />
        );
      })}
    </div>
  );
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
  const selectedModelId = useChatStore((s) => s.selectedModelId);
  const { play: playTTS, stop: stopTTS, isPlaying: isTTSPlaying, isLoading: isTTSLoading } = useAudioPlayer();
  const {
    isRecording: isCGARecording,
    recordingDuration: cgaRecordingDuration,
    audioLevel: cgaAudioLevel,
    startRecording: startCGARecording,
    stopRecording: stopCGARecording,
    cancelRecording: cancelCGARecording,
  } = useAudioRecorder();

  const extractPlainTextForTTS = useCallback((text: string): string => {
    return text
      .replace(/[#*`_~\[\]()>|-]/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }, []);

  const autoReadIfSeniorMode = useCallback((text: string) => {
    if (seniorMode && text.trim()) {
      playTTS(extractPlainTextForTTS(text));
    }
  }, [seniorMode, playTTS, extractPlainTextForTTS]);
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
  const autoReadRef = useRef<(text: string) => void>(() => {});
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

  /** 从对话文本中提取患者基本信息（年龄、性别、主诉） */
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

    const complaintPatterns = [
      /(?:不舒服|不适|问题是|症状是|主诉[：:是为为了]\s*)([^，。,\.\n]{2,30})/,
      /(?:主要是|就是|因为)([^，。,\.\n]{2,30}?)(?:不舒服|不适|疼痛|难受)/,
    ];
    for (const pattern of complaintPatterns) {
      const match = text.match(pattern);
      if (match) {
        result.chief_complaint = {
          label: "主要不适",
          value: match[1].trim(),
        };
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

  useEffect(() => {
    autoReadRef.current = autoReadIfSeniorMode;
  }, [autoReadIfSeniorMode]);

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

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
  // CGA语音答题状态
  const [cgaIsTranscribing, setCgaIsTranscribing] = useState(false);

  const cgaAutoAdvanceRef = useRef<Record<string, boolean>>({});
  const cgaKeyboardCtxRef = useRef<{
    showQuiz: boolean;
    isRecording: boolean;
    isTranscribing: boolean;
    question: ScaleQuestion | null;
    answerFn: ((q: ScaleQuestion, v: number) => void) | null;
    nextFn: (() => void) | null;
  }>({
    showQuiz: false,
    isRecording: false,
    isTranscribing: false,
    question: null,
    answerFn: null,
    nextFn: null,
  });

  // CGA：朗读当前题目
  const speakCGAQuestion = useCallback((question: ScaleQuestion) => {
    let text = `第${(cgaCurrentIndex[currentSessionId!] ?? 0) + 1}题：${question.text}。`;
    if (question.options && question.options.length > 0) {
      text += "选项：";
      question.options.forEach((opt, i) => {
        text += `${i + 1}、${opt.label}。`;
      });
    }
    playTTS(text);
  }, [cgaCurrentIndex, currentSessionId, playTTS]);

  // CGA：老年模式下自动朗读题目
  useEffect(() => {
    if (!seniorMode || !currentSessionId || chatAction !== "cga") return;
    const selectedScaleId = cgaSelectedScale[currentSessionId];
    if (!selectedScaleId || cgaCompleted[currentSessionId]) return;
    const idx = cgaCurrentIndex[currentSessionId] ?? 0;
    const scale = scales.find((s) => s.id === selectedScaleId);
    if (!scale) return;
    const question = scale.questions[idx];
    if (!question) return;
    const timer = setTimeout(() => {
      speakCGAQuestion(question);
    }, 300);
    return () => clearTimeout(timer);
  }, [seniorMode, currentSessionId, chatAction, cgaSelectedScale, cgaCurrentIndex, cgaCompleted, speakCGAQuestion]);

  useEffect(() => {
    if (!mounted) return;
    try {
      const stored = localStorage.getItem(CGA_PROGRESS_KEY);
      if (stored) {
        const allProgress = JSON.parse(stored) as Record<string, CGAProgressData>;
        const selectedScaleInit: Record<string, string> = {};
        const answersInit: Record<string, Record<string, number | number[]>> = {};
        const currentIndexInit: Record<string, number> = {};
        const completedInit: Record<string, boolean> = {};
        for (const [sid, data] of Object.entries(allProgress)) {
          if (data.selectedScale) selectedScaleInit[sid] = data.selectedScale;
          if (data.answers) answersInit[sid] = data.answers;
          if (data.currentIndex !== undefined) currentIndexInit[sid] = data.currentIndex;
          if (data.completed !== undefined) completedInit[sid] = data.completed;
        }
        /* eslint-disable react-hooks/set-state-in-effect */
        if (Object.keys(selectedScaleInit).length > 0) setCgaSelectedScale(selectedScaleInit);
        if (Object.keys(answersInit).length > 0) setCgaAnswers(answersInit);
        if (Object.keys(currentIndexInit).length > 0) setCgaCurrentIndex(currentIndexInit);
        if (Object.keys(completedInit).length > 0) setCgaCompleted(completedInit);
        /* eslint-enable react-hooks/set-state-in-effect */
      }
    } catch {
      // localStorage not available, ignore
    }
  }, [mounted]);

  const saveCGAProgress = useCallback(() => {
    if (!mounted) return;
    try {
      const allProgress: Record<string, CGAProgressData> = {};
      for (const sid of Object.keys(cgaSelectedScale)) {
        allProgress[sid] = {
          selectedScale: cgaSelectedScale[sid],
          answers: cgaAnswers[sid],
          currentIndex: cgaCurrentIndex[sid],
          completed: cgaCompleted[sid],
        };
      }
      localStorage.setItem(CGA_PROGRESS_KEY, JSON.stringify(allProgress));
    } catch {
      // localStorage not available, ignore
    }
  }, [mounted, cgaSelectedScale, cgaAnswers, cgaCurrentIndex, cgaCompleted]);

  const clearCGAProgressForSession = useCallback((sid: string) => {
    if (!mounted) return;
    try {
      const stored = localStorage.getItem(CGA_PROGRESS_KEY);
      if (stored) {
        const allProgress = JSON.parse(stored) as Record<string, CGAProgressData>;
        delete allProgress[sid];
        localStorage.setItem(CGA_PROGRESS_KEY, JSON.stringify(allProgress));
      }
    } catch {
      // localStorage not available, ignore
    }
  }, [mounted]);

  useEffect(() => {
    saveCGAProgress();
  }, [saveCGAProgress]);

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
          ],
          status: "done",
          createdAt: Date.now(),
          hasDisclaimer: true,
        };
        addMessage(aiMsg);
        setGenerating(false);
        autoReadRef.current(openingContent);
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
  }, [chatAction, currentSessionId, role, createSession, setCurrentSession, addMessage, setGenerating, cgaSelectedScale, setPanelContent, updateMessage, appendMessageText, appendPanelContent, initMessageThinking, startMessageThinkingBlock, appendMessageThinking, finalizeMessageThinking]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const ctx = cgaKeyboardCtxRef.current;
      if (!ctx.showQuiz || ctx.isRecording || ctx.isTranscribing) return;
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
        return;
      }
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9 && ctx.question && ctx.question.options && ctx.answerFn && ctx.nextFn) {
        const idx = num - 1;
        if (idx < ctx.question.options.length) {
          const opt = ctx.question.options[idx];
          ctx.answerFn(ctx.question, opt.value);
          setTimeout(() => {
            ctx.nextFn?.();
          }, 300);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

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
    const currentMsgs = currentSessionId ? useChatStore.getState().messagesBySession[currentSessionId] ?? [] : [];
    const streamingMsg = currentMsgs.find((m) => m.status === "streaming");
    if (streamingMsg) {
      streamingMsg.blocks.forEach((b) => {
        if (b.kind === "thinking" && b.data.status === "thinking") {
          finalizeMessageThinking(streamingMsg.id, b.id);
        }
      });
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
      // eslint-disable-next-line react-hooks/purity
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
        // eslint-disable-next-line react-hooks/purity
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
                  { key: "chief_complaint", label: "主要不适", value: updated.chief_complaint?.value, filled: !!updated.chief_complaint },
                ];
                addOrUpdateInfoBlock(sid, assistantMsgId, fields);
                return { ...prev, [sid]: updated };
              });
            }

            autoReadRef.current(finalReplyContent);

            if (hasFinishMarker || newRound >= MAX_COLLECT_ROUNDS) {
              setRightPanel(panelType);
              setPanelContent("");
              setGenerating(true);

              const generateReport = async () => {
                let reportSystemPrompt = "";
                if (chatAction === "prescription") {
                  reportSystemPrompt = role === "doctor"
                    ? "你是GerClaw老年科医生AI助手。请基于之前的对话信息，生成一份完整、专业、结构化的Markdown格式五大处方报告（药物处方、运动处方、营养处方、心理处方、康复处方），包含循证依据和注意事项。每个处方给出具体可执行的建议。不要在报告末尾添加免责声明，系统会自动显示。"
                    : "你是GerClaw老年科AI医生助手。请基于之前的对话信息，生成一份完整、亲切、易懂的Markdown格式五大处方报告（药物处方、运动处方、营养处方、心理处方、康复处方），用简单易懂的语言给出具体可执行的建议。不要在报告末尾添加免责声明，系统会自动显示。";
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
                      const finalReport = postprocessMedicalText(accumulatedReport);
                      setPanelContent(finalReport);
                      
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
                      autoReadRef.current(summaryText);
                    },
                    onError: () => {
                      abortControllerRef.current = null;
                      const fallbackReport = reportContent || (chatAction === "prescription" 
                        ? "# 五大处方建议\n\n## 一、药物处方\n请遵医嘱按时服药，注意观察用药反应。\n\n## 二、运动处方\n建议每天进行30分钟温和运动，如散步、太极拳。\n\n## 三、营养处方\n均衡饮食，多吃蔬菜水果，适量蛋白质。\n\n## 四、心理处方\n保持心情愉悦，多与家人朋友交流。\n\n## 五、康复处方\n根据身体状况循序渐进地进行康复训练。"
                        : "# 用药审查报告\n\n⚠️ AI辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。\n\n## 一、用药汇总\n请核对您的用药清单。\n\n## 二、潜在相互作用提示\n建议咨询专业药师。\n\n## 三、老年人用药提醒\n注意用药剂量，避免多重用药。\n\n## 四、建议\n定期复查，遵医嘱调整用药。\n\n## 五、就医建议\n如有不适请及时就医。");
                      const finalReport = postprocessMedicalText(fallbackReport);
                      setPanelContent(finalReport);
                      
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
                      autoReadRef.current(summaryText);
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
            if (finalContent.trim()) {
              finalContent += "\n\n---\n*回复中断，点击下方「重新生成」按钮继续*";
            } else {
              finalContent = "*回复中断，请点击重新生成按钮重试*";
            }
            const processedContent = postprocessMedicalText(finalContent);
            
            const updatedBlocks = currentMsg?.blocks.map((b) => {
              if (b.kind === "text" && b.id === assistantBlockId) {
                return { ...b, content: processedContent, streaming: false };
              }
              return b;
            }) ?? [];
            updateMessage(assistantMsgId, {
              status: "interrupted",
              blocks: updatedBlocks,
              hasDisclaimer: true,
            });
            setGenerating(false);
            autoReadRef.current(processedContent);
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
      // eslint-disable-next-line react-hooks/purity
      createdAt: Date.now(),
      hasDisclaimer: false,
    };
    addMessage(assistantMsg);
    initMessageThinking(assistantMsgId, initialThinkingBlockId);

    const toolCallBlockMap = new Map<string, string>();
    let allCitations: Citation[] = [];

    const buildLLMMessages = (): LLMMessage[] => {
      const llmMessages: LLMMessage[] = [];
      let systemPrompt = buildSystemPrompt(role);
      if (hasHighRisk) {
        systemPrompt += "\n\n重要提示：用户提到了高风险症状，你已经发送了紧急就医提示，请继续温和地安抚用户并强调立即就医的重要性，不要给出其他医疗建议。";
      }
      llmMessages.push({ role: "system", content: systemPrompt });

      const history = buildLLMHistory(assistantMsgId);
      llmMessages.push(...history);
      return llmMessages;
    };

    const llmMessages = buildLLMMessages();

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
          autoReadRef.current(finalContent);
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
          if (finalContent.trim()) {
            finalContent += "\n\n---\n*回复中断，点击下方「重新生成」按钮继续*";
          } else {
            finalContent = "*回复中断，请点击重新生成按钮重试*";
          }
          const processedContent = postprocessMedicalText(finalContent);

          const updatedBlocks = msgNow?.blocks.map((b) => {
            if (b.kind === "text" && b.id === assistantBlockId) {
              return { ...b, content: processedContent, streaming: false };
            }
            return b;
          }) ?? [];
          updateMessage(assistantMsgId, {
            status: "interrupted",
            blocks: updatedBlocks,
            hasDisclaimer: true,
          });
          setGenerating(false);
        },
      }
    );
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
    cgaAutoAdvanceRef.current = {};
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
      clearCGAProgressForSession(currentSessionId);
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

  /** CGA：重新评估当前量表（重置答题状态，从第一题开始） */
  const handleRestartCurrentScale = () => {
    if (!currentSessionId) return;
    stopTTS();
    cgaAutoAdvanceRef.current = {};
    setCgaAnswers((prev) => ({ ...prev, [currentSessionId]: {} }));
    setCgaCurrentIndex((prev) => ({ ...prev, [currentSessionId]: 0 }));
    setCgaCompleted((prev) => ({ ...prev, [currentSessionId]: false }));
  };

  /** CGA：重新选择量表（返回选量表界面，重置答题） */
  const handleReselectScale = () => {
    if (!currentSessionId) return;
    actionInitRef.current = null;
    clearCGAProgressForSession(currentSessionId);
    cgaAutoAdvanceRef.current = {};
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

  /** CGA：选择某个选项后，记录答案；老年模式下自动延迟跳转下一题 */
  const handleAnswerQuestion = (question: ScaleQuestion, value: number) => {
    if (!currentSessionId) return;
    stopTTS();
    const hadAnswer = !!(cgaAnswers[currentSessionId]?.[question.id] !== undefined);
    setCgaAnswers((prev) => ({
      ...prev,
      [currentSessionId]: {
        ...(prev[currentSessionId] ?? {}),
        [question.id]: value,
      },
    }));
    if (seniorMode && !hadAnswer && selectedScaleObj) {
      const currentIdx = cgaCurrentIndex[currentSessionId] ?? 0;
      const isLastQuestion = currentIdx >= selectedScaleObj.questions.length - 1;
      const autoKey = `${currentSessionId}:${question.id}`;
      if (!isLastQuestion && !cgaAutoAdvanceRef.current[autoKey]) {
        cgaAutoAdvanceRef.current[autoKey] = true;
        setTimeout(() => {
          handleNextQuestion();
        }, 600);
      }
    }
  };

  /** CGA：跳到上一题 */
  const handlePrevQuestion = () => {
    if (!currentSessionId) return;
    stopTTS();
    setCgaCurrentIndex((prev) => ({
      ...prev,
      [currentSessionId]: Math.max(0, (prev[currentSessionId] ?? 0) - 1),
    }));
  };

  /** CGA：语音答题 - 开始录音 */
  const handleCGAMicStart = async () => {
    if (cgaIsTranscribing || isCGARecording) return;
    stopTTS();
    try {
      await startCGARecording();
    } catch (err) {
      const message = err instanceof Error ? err.message : "无法启动录音";
      toast.show(message);
    }
  };

  /** CGA：语音答题 - 取消录音 */
  const handleCGARecordingCancel = () => {
    try {
      cancelCGARecording();
    } catch {
      toast.show("取消录音失败");
    }
  };

  /** CGA：语音答题 - 完成录音并识别 */
  const handleCGARecordingFinish = async () => {
    if (!currentSessionId || !currentQuestion) return;
    try {
      const blob = await stopCGARecording();
      setCgaIsTranscribing(true);
      stopTTS();
      try {
        const recognizedText = await recognizeAudio(blob);
        if (recognizedText && currentQuestion.options) {
          const matchedValue = matchCGAAnswerByVoice(recognizedText, currentQuestion.options);
          if (matchedValue !== null) {
            handleAnswerQuestion(currentQuestion, matchedValue);
            const selectedOpt = currentQuestion.options.find((o) => o.value === matchedValue);
            toast.show(`已选择：${selectedOpt?.label ?? ""}`);
            setTimeout(() => {
              handleNextQuestion();
            }, 800);
          } else {
            toast.show(`识别结果："${recognizedText}"，请手动选择选项`);
          }
        } else if (recognizedText) {
          toast.show(`识别结果："${recognizedText}"，请手动选择`);
        }
      } catch {
        toast.show("语音识别失败，请重试或手动选择");
      } finally {
        setCgaIsTranscribing(false);
      }
    } catch {
      toast.show("录音失败，请重试");
      setCgaIsTranscribing(false);
    }
  };

  /** CGA：跳到下一题（需已回答当前题）；最后一题则完成评估 */
  const handleNextQuestion = () => {
    if (!currentSessionId || !selectedScaleObj) return;
    stopTTS();
    const idx = cgaCurrentIndex[currentSessionId] ?? 0;
    if (idx >= selectedScaleObj.questions.length - 1) {
      setCgaCompleted((prev) => ({ ...prev, [currentSessionId]: true }));
      if (seniorMode) {
        playTTS("评估已完成，请在右侧查看结果。");
      }
      
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
请用Markdown格式输出，结构清晰，包含循证依据参考。不要在报告末尾添加免责声明，系统会自动显示。`
        : `你是GerClaw老年科AI医生助手，正在为老年患者解读${selectedScaleObj.fullName}（${selectedScaleObj.name}）评估结果。
请用亲切、易懂的语言为老人解释评估结果：
1. 您的得分情况说明
2. 各项回答的分析（用简单的话讲）
3. 给您的具体建议
4. 什么时候需要看医生
${phq9SuicideRisk ? "⚠️ 重要：您在最后一题提到了伤害自己的想法，请务必立即告诉家人或医生，也可以拨打心理危机干预热线：400-161-9995（全国）或 010-82951332（北京），会有人24小时帮助您。" : ""}
请用Markdown格式输出，语言温暖、易懂，避免专业术语。不要在报告末尾添加免责声明，系统会自动显示。`;

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
}`;
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

  // eslint-disable-next-line react-hooks/refs
  cgaKeyboardCtxRef.current = {
    showQuiz: showCgaQuiz,
    isRecording: isCGARecording,
    isTranscribing: cgaIsTranscribing,
    question: currentQuestion,
    answerFn: handleAnswerQuestion,
    nextFn: handleNextQuestion,
  };

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
        isCGARecording ? (
          <div className="flex-1 min-h-0 overflow-y-auto">
            <div className="max-w-2xl mx-auto px-4 py-6">
              <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                  <span className={cn("text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                    第 {(cgaCurrentIndex[currentSessionId!] ?? 0) + 1} / {selectedScaleObj.questions.length} 题 — 语音答题中
                  </span>
                </div>
              </div>
              <div className={cn(
                "rounded-xl bg-muted/70",
                seniorMode ? "px-4 py-5" : "px-3 py-4"
              )}>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={handleCGARecordingCancel}
                    className={cn(
                      "flex items-center justify-center shrink-0 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors",
                      seniorMode ? "size-14" : "size-11"
                    )}
                    aria-label="取消录音"
                  >
                    <X className={cn(seniorMode ? "size-6" : "size-5")} />
                  </button>

                  <WaveformBars audioLevel={cgaAudioLevel} recordingDuration={cgaRecordingDuration} seniorMode={seniorMode} />

                  <span className={cn(
                    "shrink-0 tabular-nums font-medium text-gray-700 dark:text-gray-300 min-w-[48px] text-center",
                    seniorMode ? "text-xl" : "text-lg"
                  )}>
                    {formatRecordingDuration(cgaRecordingDuration)}
                  </span>

                  <button
                    type="button"
                    onClick={handleCGARecordingFinish}
                    className={cn(
                      "flex items-center justify-center shrink-0 rounded-full transition-colors",
                      seniorMode ? "size-14" : "size-11",
                      "bg-indigo-600 hover:bg-indigo-700 text-white"
                    )}
                    aria-label="完成答题"
                  >
                    <Check className={cn(seniorMode ? "size-6" : "size-5")} strokeWidth={3} />
                  </button>
                </div>
                <p className={cn(
                  "text-center text-muted-foreground mt-3",
                  seniorMode ? "text-base" : "text-sm"
                )}>
                  请说出您的答案
                </p>
              </div>
            </div>
          </div>
        ) : (
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

            {/* 题目（老年模式≥18px）+ 朗读按钮 */}
            <div className="mb-6">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <h3 className={cn("font-semibold mb-1", seniorMode ? "text-xl" : "text-lg")}>
                    {currentQuestion.text}
                  </h3>
                  {currentQuestion.hint && (
                    <p className={cn("text-muted-foreground mt-1", seniorMode ? "text-base" : "text-sm")}>
                      {currentQuestion.hint}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={isTTSPlaying || isTTSLoading ? stopTTS : () => currentQuestion && speakCGAQuestion(currentQuestion)}
                  className={cn(
                    "flex items-center justify-center shrink-0 rounded-full transition-colors",
                    seniorMode ? "size-12" : "size-10",
                    isTTSPlaying
                      ? "bg-primary text-primary-foreground"
                      : isTTSLoading
                        ? "bg-muted text-muted-foreground"
                        : "bg-muted hover:bg-muted/80 text-foreground"
                  )}
                  aria-label={isTTSPlaying ? "停止朗读" : "朗读题目"}
                >
                  {isTTSLoading ? (
                    <Loader2 className={cn("animate-spin", seniorMode ? "size-5" : "size-4")} />
                  ) : isTTSPlaying ? (
                    <VolumeX className={cn(seniorMode ? "size-5" : "size-4")} />
                  ) : (
                    <Volume2 className={cn(seniorMode ? "size-5" : "size-4")} />
                  )}
                </button>
              </div>
              {cgaIsTranscribing && (
                <p className={cn("text-primary mt-2 flex items-center gap-2", seniorMode ? "text-base" : "text-sm")}>
                  <Loader2 className={cn("animate-spin", seniorMode ? "size-5" : "size-4")} />
                  正在识别语音...
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
                      "w-full flex items-start gap-3 rounded-lg border text-left transition-all",
                      seniorMode ? "p-5 min-h-[72px]" : "p-4",
                      selected
                        ? "border-primary bg-primary/10 ring-1 ring-primary"
                        : "border-border bg-card hover:border-primary/40 hover:bg-muted/40"
                    )}
                  >
                    <div
                      className={cn(
                        "flex items-center justify-center rounded-full border-2 shrink-0 mt-0.5",
                        seniorMode ? "size-9" : "size-7",
                        selected
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-muted-foreground/30"
                      )}
                    >
                      {selected && <CheckCircle2 className={cn(seniorMode ? "size-5" : "size-4")} />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className={cn("font-medium", seniorMode ? "text-lg" : "text-base")}>
                        {opt.label}
                      </div>
                      {opt.description && (
                        <div className={cn("text-muted-foreground mt-0.5", seniorMode ? "text-sm" : "text-xs")}>
                          {opt.description}
                        </div>
                      )}
                    </div>
                    {opt.value > 0 && (
                      <span className={cn("text-muted-foreground shrink-0", seniorMode ? "text-sm" : "text-xs")}>
                        {opt.value} 分
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* 上一题 / 语音答题 / 下一题（适老化大按钮≥48px） */}
            <div className="flex items-center justify-between mt-8 gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePrevQuestion}
                disabled={(cgaCurrentIndex[currentSessionId!] ?? 0) === 0}
                className={cn("shrink-0", seniorMode ? "min-h-12 px-5 text-base" : "h-9 px-3 text-sm")}
                aria-label="上一题"
              >
                ← 上一题
              </Button>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleReselectScale}
                  className={cn(
                    "text-muted-foreground hover:text-foreground",
                    seniorMode ? "text-base min-h-12 px-2" : "text-sm"
                  )}
                >
                  重选量表
                </button>
                <button
                  type="button"
                  onClick={handleCGAMicStart}
                  disabled={cgaIsTranscribing}
                  className={cn(
                    "flex items-center justify-center gap-2 rounded-full transition-colors font-medium",
                    seniorMode ? "h-12 px-5 text-base" : "h-10 px-4 text-sm",
                    cgaIsTranscribing
                      ? "bg-muted text-muted-foreground cursor-not-allowed"
                      : "bg-rose-500 hover:bg-rose-600 text-white shadow-md"
                  )}
                  aria-label="语音答题"
                >
                  {cgaIsTranscribing ? (
                    <>
                      <Loader2 className={cn("animate-spin", seniorMode ? "size-5" : "size-4")} />
                      识别中
                    </>
                  ) : (
                    <>
                      <Mic className={cn(seniorMode ? "size-5" : "size-4")} />
                      {seniorMode ? "语音答题" : ""}
                    </>
                  )}
                </button>
                {currentAnswers[currentQuestion.id] !== undefined && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={handleNextQuestion}
                    className={cn(
                      "shrink-0",
                      seniorMode ? "min-h-12 px-6 text-base" : "h-9 px-3 text-sm"
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

            <div className={cn("mt-8 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30 px-3 py-2 text-amber-800 dark:text-amber-200", seniorMode ? "text-sm" : "text-xs")}>
              AI 评估仅供健康参考，不能替代医生诊断。身体不适请及时就医。
            </div>
          </div>
        </div>
        )
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
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                onClick={doExitAction}
                className={cn(
                  "rounded-md border border-border hover:bg-muted",
                  seniorMode ? "min-h-12 px-6 text-base py-3" : "px-4 py-2 text-sm"
                )}
              >
                返回对话
              </button>
              <button
                type="button"
                onClick={handleRestartCurrentScale}
                className={cn(
                  "rounded-md border border-border hover:bg-muted",
                  seniorMode ? "min-h-12 px-6 text-base py-3" : "px-4 py-2 text-sm"
                )}
              >
                重新评估
              </button>
              <button
                type="button"
                onClick={handleReselectScale}
                className={cn(
                  "rounded-md border border-border hover:bg-muted",
                  seniorMode ? "min-h-12 px-6 text-base py-3" : "px-4 py-2 text-sm"
                )}
              >
                继续评估其他量表
              </button>
              <button
                type="button"
                onClick={() => setRightPanel("cga")}
                className={cn(
                  "rounded-md bg-primary text-primary-foreground hover:bg-primary/90",
                  seniorMode ? "min-h-12 px-6 text-base py-3" : "px-4 py-2 text-sm"
                )}
              >
                查看评估报告 →
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col">
          {messages.length > 0 && <MessageList messages={messages} onRegenerate={handleRegenerate} />}
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
