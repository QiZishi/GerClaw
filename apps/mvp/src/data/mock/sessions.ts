/**
 * Mock 会话数据
 * 用于侧边栏历史对话列表展示
 */
import type { Session } from "@/types";

const now = Date.now();
const DAY = 24 * 60 * 60 * 1000;
const HOUR = 60 * 60 * 1000;
const MINUTE = 60 * 1000;

export const mockSessions: Session[] = [
  // === 今天 ===
  {
    id: "sess_today_1",
    title: "血压偏高咨询",
    role: "patient",
    createdAt: now - 30 * MINUTE,
    updatedAt: now - 5 * MINUTE,
    lastMessagePreview: "建议您每天定时监测血压，并记录数值变化…",
    messageCount: 8,
    pinned: true,
    panelType: "prescription",
  },
  {
    id: "sess_today_2",
    title: "老年用药方案评估",
    role: "doctor",
    createdAt: now - 2 * HOUR,
    updatedAt: now - 30 * MINUTE,
    lastMessagePreview: "已为该患者生成五大处方草案，请审阅…",
    messageCount: 12,
    panelType: "prescription",
  },
  {
    id: "sess_today_3",
    title: "头晕乏力症状分析",
    role: "patient",
    createdAt: now - 4 * HOUR,
    updatedAt: now - 3 * HOUR,
    lastMessagePreview: "结合您的描述，建议进一步检查血常规…",
    messageCount: 6,
  },
  // === 昨天 ===
  {
    id: "sess_yesterday_1",
    title: "糖尿病饮食建议",
    role: "patient",
    createdAt: now - DAY - 2 * HOUR,
    updatedAt: now - DAY,
    lastMessagePreview: "糖尿病患者应控制碳水化合物摄入…",
    messageCount: 10,
    panelType: "health-profile",
  },
  {
    id: "sess_yesterday_2",
    title: "CGA 评估 - 张大爷",
    role: "doctor",
    createdAt: now - DAY - 5 * HOUR,
    updatedAt: now - DAY - 1 * HOUR,
    lastMessagePreview: "老年综合评估完成，日常生活能力下降…",
    messageCount: 15,
    panelType: "cga",
  },
  // === 最近7天 ===
  {
    id: "sess_7d_1",
    title: "关节疼痛咨询",
    role: "patient",
    createdAt: now - 3 * DAY,
    updatedAt: now - 3 * DAY + 2 * HOUR,
    lastMessagePreview: "可适当进行低强度运动，如散步、太极…",
    messageCount: 7,
  },
  {
    id: "sess_7d_2",
    title: "用药相互作用审查",
    role: "doctor",
    createdAt: now - 4 * DAY,
    updatedAt: now - 4 * DAY + 1 * HOUR,
    lastMessagePreview: "检测到 2 种药物存在中等程度相互作用…",
    messageCount: 9,
    panelType: "prescription",
  },
  {
    id: "sess_7d_3",
    title: "睡眠质量改善",
    role: "patient",
    createdAt: now - 5 * DAY,
    updatedAt: now - 5 * DAY + 3 * HOUR,
    lastMessagePreview: "建议保持规律作息，避免睡前饮用浓茶…",
    messageCount: 5,
  },
  // === 更早 ===
  {
    id: "sess_older_1",
    title: "体检报告解读",
    role: "patient",
    createdAt: now - 15 * DAY,
    updatedAt: now - 15 * DAY + 1 * HOUR,
    lastMessagePreview: "您的血脂略偏高，建议调整饮食结构…",
    messageCount: 11,
  },
  {
    id: "sess_older_2",
    title: "多病共存患者管理",
    role: "doctor",
    createdAt: now - 20 * DAY,
    updatedAt: now - 20 * DAY + 2 * HOUR,
    lastMessagePreview: "针对该多病共存患者，建议优先管理…",
    messageCount: 18,
  },
];
