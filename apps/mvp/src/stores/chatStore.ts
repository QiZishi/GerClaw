/**
 * 对话状态 store
 * 对齐 gerclaw设计要求.md §4.1 通用对话 / §3.3 主聊天区
 * 管理：会话列表/消息/当前会话
 * 支持 localStorage 持久化
 */
import { create } from "zustand";
import type { Message, Session } from "@/types";
import { generateId } from "@/lib/format";

const STORAGE_KEYS = {
  sessions: "gerclaw_sessions",
  messages: "gerclaw_messages",
} as const;

const MAX_MESSAGES_PER_SESSION = 50;

function loadFromStorage<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    try {
      window.localStorage.removeItem(key);
    } catch {
      // ignore
    }
    return fallback;
  }
}

function saveToStorage<T>(key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // silently fail
  }
}

function truncateMessages(messagesBySession: Record<string, Message[]>): Record<string, Message[]> {
  const result: Record<string, Message[]> = {};
  for (const [sid, msgs] of Object.entries(messagesBySession)) {
    result[sid] = msgs.slice(-MAX_MESSAGES_PER_SESSION);
  }
  return result;
}

function sortSessions(sessions: Session[]): Session[] {
  return [...sessions].sort((a, b) => {
    if (a.pinned && !b.pinned) return -1;
    if (!a.pinned && b.pinned) return 1;
    return b.updatedAt - a.updatedAt;
  });
}

function getTextPreview(message: Message): string {
  return message.blocks
    .filter((b) => b.kind === "text")
    .map((b) => (b as { content: string }).content)
    .join(" ")
    .slice(0, 60);
}

interface ChatState {
  // === 会话列表 ===
  sessions: Session[];
  setSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  updateSession: (id: string, patch: Partial<Session>) => void;
  removeSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  togglePinSession: (id: string) => void;

  // === 消息 ===
  /** sessionId -> messages 映射 */
  messagesBySession: Record<string, Message[]>;
  setMessages: (sessionId: string, messages: Message[]) => void;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, patch: Partial<Message>) => void;
  removeMessage: (id: string) => void;
  getMessages: (sessionId: string) => Message[];

  // === 流式生成状态 ===
  isGenerating: boolean;
  setGenerating: (generating: boolean) => void;

  // === 便捷方法 ===
  createSession: (role?: Session["role"]) => string;
  clearAllData: () => void;
}

const initialSessions = loadFromStorage<Session[]>(STORAGE_KEYS.sessions, []);
const initialMessages = loadFromStorage<Record<string, Message[]>>(STORAGE_KEYS.messages, {});

export const useChatStore = create<ChatState>()((set, get) => ({
  // === 会话列表 ===
  sessions: sortSessions(initialSessions),
  setSessions: (sessions) => {
    const sorted = sortSessions(sessions);
    set({ sessions: sorted });
    saveToStorage(STORAGE_KEYS.sessions, sorted);
  },
  addSession: (session) =>
    set((s) => {
      const next = sortSessions([session, ...s.sessions]);
      saveToStorage(STORAGE_KEYS.sessions, next);
      return { sessions: next };
    }),
  updateSession: (id, patch) =>
    set((s) => {
      const updated = s.sessions.map((sess) =>
        sess.id === id ? { ...sess, ...patch, updatedAt: Date.now() } : sess
      );
      const sorted = sortSessions(updated);
      saveToStorage(STORAGE_KEYS.sessions, sorted);
      return { sessions: sorted };
    }),
  removeSession: (id) =>
    set((s) => {
      const nextMsgs = { ...s.messagesBySession };
      delete nextMsgs[id];
      const truncated = truncateMessages(nextMsgs);
      saveToStorage(STORAGE_KEYS.messages, truncated);
      const nextSessions = sortSessions(s.sessions.filter((sess) => sess.id !== id));
      saveToStorage(STORAGE_KEYS.sessions, nextSessions);
      return {
        sessions: nextSessions,
        messagesBySession: truncated,
      };
    }),
  renameSession: (id, title) =>
    set((s) => {
      const updated = s.sessions.map((sess) =>
        sess.id === id ? { ...sess, title, updatedAt: Date.now() } : sess
      );
      const sorted = sortSessions(updated);
      saveToStorage(STORAGE_KEYS.sessions, sorted);
      return { sessions: sorted };
    }),
  togglePinSession: (id) =>
    set((s) => {
      const updated = s.sessions.map((sess) =>
        sess.id === id ? { ...sess, pinned: !sess.pinned } : sess
      );
      const sorted = sortSessions(updated);
      saveToStorage(STORAGE_KEYS.sessions, sorted);
      return { sessions: sorted };
    }),

  // === 消息 ===
  messagesBySession: truncateMessages(initialMessages),
  setMessages: (sessionId, messages) =>
    set((s) => {
      const next = { ...s.messagesBySession, [sessionId]: messages };
      const truncated = truncateMessages(next);
      saveToStorage(STORAGE_KEYS.messages, truncated);
      return { messagesBySession: truncated };
    }),
  addMessage: (message) =>
    set((s) => {
      const existing = s.messagesBySession[message.sessionId] ?? [];
      const updated = [...existing, message];
      const next = { ...s.messagesBySession, [message.sessionId]: updated };
      const truncated = truncateMessages(next);
      saveToStorage(STORAGE_KEYS.messages, truncated);

      const updatedSessions = s.sessions.map((sess) =>
        sess.id === message.sessionId
          ? {
              ...sess,
              updatedAt: Date.now(),
              messageCount: (sess.messageCount ?? 0) + 1,
              lastMessagePreview: getTextPreview(message),
            }
          : sess
      );
      const sorted = sortSessions(updatedSessions);
      saveToStorage(STORAGE_KEYS.sessions, sorted);

      return { messagesBySession: truncated, sessions: sorted };
    }),
  updateMessage: (id, patch) =>
    set((s) => {
      const next = { ...s.messagesBySession };
      for (const sid of Object.keys(next)) {
        next[sid] = next[sid].map((m) =>
          m.id === id ? { ...m, ...patch } : m
        );
      }
      const truncated = truncateMessages(next);
      saveToStorage(STORAGE_KEYS.messages, truncated);
      return { messagesBySession: truncated };
    }),
  removeMessage: (id) =>
    set((s) => {
      const next = { ...s.messagesBySession };
      for (const sid of Object.keys(next)) {
        next[sid] = next[sid].filter((m) => m.id !== id);
      }
      const truncated = truncateMessages(next);
      saveToStorage(STORAGE_KEYS.messages, truncated);
      return { messagesBySession: truncated };
    }),
  getMessages: (sessionId) => get().messagesBySession[sessionId] ?? [],

  // === 流式生成状态 ===
  isGenerating: false,
  setGenerating: (isGenerating) => set({ isGenerating }),

  // === 便捷方法 ===
  createSession: (role = "patient") => {
    const id = generateId("session");
    const now = Date.now();
    const session: Session = {
      id,
      title: "新对话",
      role,
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
    };
    set((s) => {
      const nextSessions = sortSessions([session, ...s.sessions]);
      saveToStorage(STORAGE_KEYS.sessions, nextSessions);
      const nextMsgs = { ...s.messagesBySession, [id]: [] };
      const truncated = truncateMessages(nextMsgs);
      saveToStorage(STORAGE_KEYS.messages, truncated);
      return {
        sessions: nextSessions,
        messagesBySession: truncated,
      };
    });
    return id;
  },

  clearAllData: () => {
    if (typeof window !== "undefined") {
      try {
        window.localStorage.removeItem(STORAGE_KEYS.sessions);
        window.localStorage.removeItem(STORAGE_KEYS.messages);
      } catch {
        // ignore
      }
    }
    set({ sessions: [], messagesBySession: {} });
  },
}));
