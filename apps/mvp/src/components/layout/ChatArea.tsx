"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
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
import { mockMessagesBySession } from "@/data/mock/messages";
import { mockSessions } from "@/data/mock/sessions";
import { mockScales } from "@/data/mock/cga";
import { cn } from "@/lib/utils";
import { HIGH_RISK_SYMPTOMS, EMERGENCY_ALERT } from "@/lib/constants";
import type { ChatActionType, Message, Scale, ScaleQuestion } from "@/types";
import { generateId } from "@/lib/format";

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

/** 需要收集的字段定义 */
interface FieldDef {
  key: string;
  label: string;
  /** 患者端提问话术（亲切、易懂）*/
  patientPrompt: string;
  /** 医生端提问话术（专业、简洁）*/
  doctorPrompt: string;
}

/** 五大处方需要收集的字段 */
const PRESCRIPTION_FIELDS: FieldDef[] = [
  {
    key: "age",
    label: "年龄",
    patientPrompt: "请问您今年多大年纪啦？",
    doctorPrompt: "患者年龄？",
  },
  {
    key: "gender",
    label: "性别",
    patientPrompt: "请问您是男性还是女性呀？",
    doctorPrompt: "患者性别？",
  },
  {
    key: "chiefComplaint",
    label: "主要不适",
    patientPrompt:
      "您现在哪里不舒服呢？可以跟我详细说说，比如哪里疼、有什么症状？",
    doctorPrompt: "主诉？",
  },
  {
    key: "history",
    label: "既往病史",
    patientPrompt:
      "您以前有没有得过什么慢性病呀？比如高血压、糖尿病这些？",
    doctorPrompt: "既往病史？",
  },
  {
    key: "currentMedications",
    label: "当前用药",
    patientPrompt: "您现在有没有在吃什么药呢？药名是什么呀？",
    doctorPrompt: "当前用药方案？",
  },
  {
    key: "allergies",
    label: "过敏史",
    patientPrompt: "您有没有对什么药物或者食物过敏的情况？",
    doctorPrompt: "过敏史？",
  },
];

/** CGA 评估需要收集的字段 */
const CGA_FIELDS: FieldDef[] = [
  {
    key: "age",
    label: "年龄",
    patientPrompt: "请问您今年多大年纪啦？",
    doctorPrompt: "患者年龄？",
  },
  {
    key: "livingStatus",
    label: "居住情况",
    patientPrompt: "您现在是自己住还是和家人一起住呀？日常生活能自己照顾自己吗？",
    doctorPrompt: "居住情况与ADL/IADL？",
  },
  {
    key: "cognitive",
    label: "认知状态",
    patientPrompt: "您最近记忆力怎么样？有没有经常忘事的情况？",
    doctorPrompt: "认知功能筛查结果？",
  },
  {
    key: "mood",
    label: "情绪状态",
    patientPrompt: "最近心情怎么样？会不会经常觉得闷闷不乐或者焦虑？",
    doctorPrompt: "情绪/抑郁筛查？",
  },
  {
    key: "mobility",
    label: "活动能力",
    patientPrompt: "走路稳不稳？最近半年有没有摔倒过？",
    doctorPrompt: "跌倒史与步态？",
  },
  {
    key: "nutrition",
    label: "营养状况",
    patientPrompt: "最近吃饭怎么样？体重有没有明显变化？",
    doctorPrompt: "营养评估（MNA-SF）？",
  },
];

/** 用药审查需要收集的字段 */
const DRUG_REVIEW_FIELDS: FieldDef[] = [
  {
    key: "drugs",
    label: "用药清单",
    patientPrompt:
      "请把您正在吃的所有药告诉我好吗？包括药名、每次吃多少、一天吃几次。也可以上传药盒照片。",
    doctorPrompt: "请输入或上传患者完整用药清单。",
  },
  {
    key: "condition",
    label: "诊断/病情",
    patientPrompt: "这些药是治什么病的呀？医生当时怎么跟您说的？",
    doctorPrompt: "患者诊断与用药目的？",
  },
  {
    key: "symptoms",
    label: "不良反应",
    patientPrompt: "吃药之后有没有觉得哪里不舒服？比如头晕、恶心、皮疹这些？",
    doctorPrompt: "有无不良反应或不适？",
  },
];

/** 健康画像需要收集的字段（医生端查询患者档案；患者端直接展示自己的档案） */
const HEALTH_PROFILE_FIELDS: FieldDef[] = [
  {
    key: "patientId",
    label: "患者标识",
    patientPrompt: "",
    doctorPrompt: "请输入患者姓名或身份证号以查询健康档案。",
  },
  {
    key: "confirmView",
    label: "确认查看",
    patientPrompt: "好的，您的健康档案如下，请过目。如果有需要补充或修改的信息，随时告诉我。",
    doctorPrompt: "",
  },
];

/** 获取某个功能需要收集的字段 */
function getFieldsForAction(action: ChatActionType): FieldDef[] {
  switch (action) {
    case "prescription":
      return PRESCRIPTION_FIELDS;
    case "cga":
      return CGA_FIELDS;
    case "drug-review":
      return DRUG_REVIEW_FIELDS;
    case "health-profile":
      return HEALTH_PROFILE_FIELDS;
    default:
      return [];
  }
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

/** 根据已收集的字段，模拟 AI 追问下一个缺失字段 */
function getNextPrompt(
  action: ChatActionType,
  collectedKeys: Set<string>,
  role: "patient" | "doctor" | "visitor"
): string | null {
  const fields = getFieldsForAction(action);
  const isPatient = role !== "doctor";
  for (const f of fields) {
    if (!collectedKeys.has(f.key)) {
      return isPatient ? f.patientPrompt : f.doctorPrompt;
    }
  }
  return null;
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
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const setGenerating = useChatStore((s) => s.setGenerating);
  const messagesBySession = useChatStore((s) => s.messagesBySession);
  const addMessage = useChatStore((s) => s.addMessage);
  const createSession = useChatStore((s) => s.createSession);
  const storeSessions = useChatStore((s) => s.sessions);

  // 各功能已收集的字段（sessionId -> { fieldKey: value }）
  const [collectedFields, setCollectedFields] = useState<
    Record<string, Record<string, string>>
  >({});
  // 各会话功能模式下的对话轮次计数（sessionId -> count），§6.4 上限5轮
  const [collectRounds, setCollectRounds] = useState<Record<string, number>>({});
  /** 信息补全上限轮次（设计要求10轮，经用户确认调整为5轮以适配老年患者） */
  const MAX_COLLECT_ROUNDS = 5;
  const actionInitRef = useRef<string | null>(null); // 记录是否已为当前 action 发送开场消息

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

  // store 中的消息 + mock 消息合并
  const messages: Message[] = currentSessionId
    ? messagesBySession[currentSessionId] ??
      mockMessagesBySession[currentSessionId] ??
      []
    : [];

  // 当前会话标题
  const currentSessionTitle = (() => {
    if (!currentSessionId) return "";
    const fromStore = storeSessions.find((s) => s.id === currentSessionId);
    if (fromStore) return fromStore.title;
    const fromMock = mockSessions.find((s) => s.id === currentSessionId);
    return fromMock?.title ?? "";
  })();

  // 选中会话时，若 store 无消息但有 mock，加载到 store
  useEffect(() => {
    if (!currentSessionId) return;
    if (messagesBySession[currentSessionId]) return;
    const mock = mockMessagesBySession[currentSessionId];
    if (mock) {
      for (const m of mock) addMessage(m);
    }
    // 切换会话时重置开场标记
    actionInitRef.current = null;
  }, [currentSessionId, messagesBySession, addMessage]);

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

    // 健康画像 + 患者端：直接展示个人档案，无需收集信息
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
              content:
                "好的，您的健康档案如下，请过目。如果有需要补充或修改的信息，随时告诉我。",
            },
          ],
          status: "done",
          createdAt: Date.now(),
          hasDisclaimer: true,
        };
        addMessage(aiMsg);
        setGenerating(false);
        // 直接展开右侧面板展示健康画像
        setTimeout(() => {
          const { setRightPanel } = useAppStore.getState();
          setRightPanel("health-profile");
        }, 600);
      }, 600);
      return;
    }

    const initKey = `${sid}:${chatAction}`;
    if (actionInitRef.current === initKey) return;
    actionInitRef.current = initKey;

    // 延迟发送开场消息（模拟 AI 思考）
    setGenerating(true);
    setTimeout(() => {
      setCollectedFields((prev) => {
        if (prev[sid!]) return prev;
        return { ...prev, [sid!]: {} };
      });
      const aiMsg: Message = {
        id: generateId("msg"),
        sessionId: sid!,
        role: "assistant",
        blocks: [
          {
            kind: "text",
            id: generateId("block"),
            content: getOpeningMessage(chatAction, role),
          },
        ],
        status: "done",
        createdAt: Date.now(),
        hasDisclaimer: true,
      };
      addMessage(aiMsg);
      setGenerating(false);
    }, 600);
  }, [chatAction, currentSessionId, role, createSession, setCurrentSession, addMessage, setGenerating, cgaSelectedScale]);

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

  const handleSend = (text: string) => {
    if (!currentSessionId) {
      // 无会话时先创建
      const sid = createSession(role);
      setCurrentSession(sid);
      // 延迟一下让会话创建完成再发送
      setTimeout(() => doSend(sid, text), 50);
      return;
    }
    doSend(currentSessionId, text);
  };

  const doSend = (sid: string, text: string) => {
    const userMsg: Message = {
      id: generateId("msg"),
      sessionId: sid,
      role: "user",
      blocks: [{ kind: "text", id: generateId("block"), content: text }],
      status: "done",
      createdAt: Date.now(),
    };
    addMessage(userMsg);
    setGenerating(true);

    // 铁律5：高风险症状检测，立即就医强提示
    const highRisk = detectHighRiskSymptoms(text);
    if (highRisk.length > 0) {
      setTimeout(() => {
        const emMsg = buildEmergencyMessage(highRisk, role);
        emMsg.sessionId = sid;
        addMessage(emMsg);
        setGenerating(false);
      }, 600);
      return;
    }

    // 在功能模式下：模拟信息提取+追问
    if (chatAction !== "none") {
      setTimeout(() => {
        // 模拟"提取"了一些信息（简单关键词匹配，mock 阶段）
        const prev = collectedFields[sid] ?? {};
        const collected = { ...prev };
        const fields = getFieldsForAction(chatAction);

        // 简单 mock 提取
        if (fields.find((f) => f.key === "age")) {
          const ageMatch = text.match(/(\d{2})\s*岁/);
          if (ageMatch) collected.age = ageMatch[1];
          if (/\d{2}/.test(text) && !collected.age) {
            const m = text.match(/(\d{2})/);
            if (m && parseInt(m[1]) >= 40 && parseInt(m[1]) <= 120) {
              collected.age = m[1];
            }
          }
        }
        if (fields.find((f) => f.key === "gender")) {
          if (/女|女性|女士|妈妈|奶奶|婆婆/.test(text)) collected.gender = "女";
          else if (/男|男性|先生|爸爸|爷爷/.test(text)) collected.gender = "男";
        }
        if (fields.find((f) => f.key === "chiefComplaint")) {
          if (text.length > 4 && !collected.chiefComplaint) {
            collected.chiefComplaint = text.slice(0, 30);
          }
        }
        if (fields.find((f) => f.key === "drugs")) {
          if (!collected.drugs) collected.drugs = text.slice(0, 50);
        }
        if (fields.find((f) => f.key === "patientId")) {
          if (!collected.patientId) collected.patientId = text.trim();
        }

        // 更新收集的字段 + 累计轮次
        setCollectedFields((prev2) => ({ ...prev2, [sid]: collected }));
        const newRound = (collectRounds[sid] ?? 0) + 1;
        setCollectRounds((prev) => ({ ...prev, [sid]: newRound }));

        const collectedSet = new Set(
          Object.keys(collected).filter((k) => collected[k])
        );

        // 判断是否收集完毕
        let nextPrompt = getNextPrompt(chatAction, collectedSet, role);
        // §6.4 上限5轮：达到上限仍有缺失字段时，用已有信息强制生成
        const reachedLimit = newRound >= MAX_COLLECT_ROUNDS;
        if (nextPrompt && reachedLimit) {
          nextPrompt = null;
        }

        let replyContent: string;
        let willFinish = false;

        if (nextPrompt) {
          // 还有字段缺失，追问
          const collectedList = Object.entries(collected)
            .filter(([, v]) => v)
            .map(([k, v]) => {
              const f = fields.find((ff) => ff.key === k);
              return f ? `${f.label}：${v}` : "";
            })
            .filter(Boolean)
            .join("、");
          const prefix = collectedList
            ? role === "doctor"
              ? `已记录：${collectedList}。`
              : `好的，我已经记录了：${collectedList}。`
            : role === "doctor"
              ? "收到。"
              : "好的，我收到了。";
          replyContent = `${prefix}\n\n${nextPrompt}`;
        } else {
          // 信息收集完毕（或达到上限）
          willFinish = true;
          if (reachedLimit) {
            replyContent =
              role === "doctor"
                ? `已收集 ${newRound} 轮信息，将基于现有信息生成结果，请稍候…`
                : `好的，我已经了解了您的整体情况，正在为您生成建议，请稍等一下哦～`;
          } else {
            replyContent =
              role === "doctor"
                ? "信息收集完毕，正在为您生成结果，请稍候…"
                : "好的，您的信息我都了解了，正在为您生成建议，请稍等一下哦～";
          }
        }

        const aiMsg: Message = {
          id: generateId("msg"),
          sessionId: sid,
          role: "assistant",
          blocks: [
            {
              kind: "text",
              id: generateId("block"),
              content: replyContent,
            },
          ],
          status: "done",
          createdAt: Date.now(),
          hasDisclaimer: true,
        };
        addMessage(aiMsg);
        setGenerating(false);

        // 如果收集完毕，模拟生成后发送摘要+查看报告按钮，并展开右侧面板
        if (willFinish) {
          setTimeout(() => {
            const panelType = chatAction as
              | "prescription"
              | "cga"
              | "health-profile"
              | "drug-review";
            const panelLabels: Record<string, string> = {
              prescription: "查看完整处方",
              cga: "查看评估报告",
              "health-profile": "查看健康画像",
              "drug-review": "查看审查结果",
            };
            const summaryText =
              role === "doctor"
                ? "结果已生成完毕，包含关键结论和建议。可点击下方按钮查看完整报告。"
                : "好的，您的建议已经生成好啦！我帮您总结了关键内容，您可以点击下方按钮查看完整报告。";
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
                  summary:
                    role === "doctor"
                      ? "完整结果已生成，包含处方/评估/审查详情。"
                      : "完整结果已生成，您可以查看详情。",
                  buttonLabel: panelLabels[panelType] ?? "查看完整报告",
                  panelType,
                },
              ],
              status: "done",
              createdAt: Date.now(),
              hasDisclaimer: true,
            };
            addMessage(summaryMsg);
            const { setRightPanel } = useAppStore.getState();
            setRightPanel(panelType);
            setChatAction("none");
          }, 1500);
        }
      }, 1000);
    } else {
      // 普通聊天模式
      setTimeout(() => {
        const aiMsg: Message = {
          id: generateId("msg"),
          sessionId: sid,
          role: "assistant",
          blocks: [
            {
              kind: "text",
              id: generateId("block"),
              content:
                "已收到您的咨询，正在为您分析…（占位回复，后续接入真实 LLM）",
            },
          ],
          status: "done",
          createdAt: Date.now(),
          hasDisclaimer: true,
        };
        addMessage(aiMsg);
        setGenerating(false);
      }, 1200);
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
      setCollectedFields((prev) => {
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
      // 已是最后一题且已作答，完成评估
      setCgaCompleted((prev) => ({ ...prev, [currentSessionId]: true }));
      setTimeout(() => {
        const { setRightPanel } = useAppStore.getState();
        setRightPanel("cga");
      }, 600);
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

  // 当前会话已收集的字段
  const currentCollected = currentSessionId
    ? collectedFields[currentSessionId] ?? {}
    : {};
  const fields = getFieldsForAction(chatAction);

  // 当前选中的量表
  const selectedScaleObj =
    chatAction === "cga" && currentSessionId
      ? mockScales.find((s) => s.id === cgaSelectedScale[currentSessionId])
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
            <ScaleSelector scales={mockScales} onSelect={handleSelectScale} />
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
              {selectedScaleObj.fullName} 已完成，评估结果已生成在右侧面板。
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
                onClick={handleExitAction}
                className={cn(
                  "px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90",
                  seniorMode && "text-base py-3 px-6"
                )}
              >
                完成
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto">
          {messages.length > 0 && <MessageList messages={messages} />}

          {/* 功能模式：AI 正在生成时的加载提示 */}
          {chatAction !== "none" && isGenerating && (
            <div className="px-4 py-2 max-w-3xl mx-auto">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                AI 正在分析…
              </div>
            </div>
          )}

          {/* 功能模式底部进度条（非生成状态时显示，仅非 CGA 功能）*/}
          {chatAction !== "none" && chatAction !== "cga" && !isGenerating && fields.length > 0 && (
            <div className="border-t border-border/60 bg-muted/20 px-4 py-3">
              <div className="max-w-3xl mx-auto">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">
                    {actionTitles[chatAction]} — 信息收集进度
                    <span className="text-xs text-muted-foreground ml-2">
                      （第 {(collectRounds[currentSessionId!] ?? 0)} / {MAX_COLLECT_ROUNDS} 轮）
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={handleExitAction}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    退出
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {fields.map((f) => {
                    const filled = !!currentCollected[f.key];
                    return (
                      <div
                        key={f.key}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs border",
                          filled
                            ? "bg-primary/10 border-primary/30 text-primary"
                            : "bg-muted border-border text-muted-foreground"
                        )}
                      >
                        {filled ? (
                          <CheckCircle2 className="size-3" />
                        ) : (
                          <Circle className="size-3" />
                        )}
                        {f.label}
                      </div>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {role === "doctor"
                    ? "请继续提供患者信息，系统将自动提取缺失字段。信息充分后自动生成结果。"
                    : "您可以继续跟我聊天或者上传病历、检查报告，缺少的信息我会主动问您～"}
                </p>
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
          onStop={() => setGenerating(false)}
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
