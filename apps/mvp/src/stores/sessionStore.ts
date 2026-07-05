/**
 * 会话持久化 store
 * 对齐 FRONTEND.md §4 状态管理规范（Zustand stores 通过 localStorage 中间件持久化）
 * 单独抽出，避免 appStore 过大；实际持久化通过 zustand persist 中间件实现
 *
 * 注意：本文件提供显式的 save/load 接口，用于在适当时机手动同步（如刷新前）
 */
import { useChatStore } from "./chatStore";
import { storage, STORAGE_KEYS } from "@/lib/storage";
import type { Message, Session } from "@/types";

/** 持久化当前所有会话与消息到 localStorage */
export function persistSessions(): void {
  const { sessions } = useChatStore.getState();
  const { messagesBySession } = useChatStore.getState();
  storage.set(STORAGE_KEYS.sessions, sessions);
  storage.set(STORAGE_KEYS.messages, messagesBySession);
}

/** 从 localStorage 恢复会话与消息 */
export function restoreSessions(): {
  sessions: Session[];
  messagesBySession: Record<string, Message[]>;
} {
  const sessions = storage.get<Session[]>(STORAGE_KEYS.sessions, []);
  const messagesBySession = storage.get<Record<string, Message[]>>(
    STORAGE_KEYS.messages,
    {}
  );
  return { sessions, messagesBySession };
}

/** 清空所有持久化的会话数据 */
export function clearPersistedSessions(): void {
  storage.remove(STORAGE_KEYS.sessions);
  storage.remove(STORAGE_KEYS.messages);
}

/** 将恢复的数据加载到 chatStore */
export function loadSessionsIntoStore(): void {
  const { sessions, messagesBySession } = restoreSessions();
  useChatStore.getState().setSessions(sessions);
  // 批量设置消息
  for (const [sid, msgs] of Object.entries(messagesBySession)) {
    useChatStore.getState().setMessages(sid, msgs);
  }
}
