/**
 * 对话状态 store
 * 对齐 gerclaw设计要求.md §4.1 通用对话 / §3.3 主聊天区
 * 管理：会话列表/消息/当前会话
 */
import { create } from "zustand";
import type { Message, Session } from "@/types";
import { generateId } from "@/lib/format";

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
}

export const useChatStore = create<ChatState>()((set, get) => ({
  // === 会话列表 ===
  sessions: [],
  setSessions: (sessions) => set({ sessions }),
  addSession: (session) =>
    set((s) => ({ sessions: [session, ...s.sessions] })),
  updateSession: (id, patch) =>
    set((s) => ({
      sessions: s.sessions.map((sess) =>
        sess.id === id ? { ...sess, ...patch } : sess
      ),
    })),
  removeSession: (id) =>
    set((s) => {
      const next = { ...s.messagesBySession };
      delete next[id];
      return {
        sessions: s.sessions.filter((sess) => sess.id !== id),
        messagesBySession: next,
      };
    }),
  renameSession: (id, title) =>
    set((s) => ({
      sessions: s.sessions.map((sess) =>
        sess.id === id ? { ...sess, title } : sess
      ),
    })),
  togglePinSession: (id) =>
    set((s) => ({
      sessions: s.sessions.map((sess) =>
        sess.id === id ? { ...sess, pinned: !sess.pinned } : sess
      ),
    })),

  // === 消息 ===
  messagesBySession: {},
  setMessages: (sessionId, messages) =>
    set((s) => ({
      messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
    })),
  addMessage: (message) =>
    set((s) => ({
      messagesBySession: {
        ...s.messagesBySession,
        [message.sessionId]: [
          ...(s.messagesBySession[message.sessionId] ?? []),
          message,
        ],
      },
    })),
  updateMessage: (id, patch) =>
    set((s) => {
      const next = { ...s.messagesBySession };
      for (const sid of Object.keys(next)) {
        next[sid] = next[sid].map((m) =>
          m.id === id ? { ...m, ...patch } : m
        );
      }
      return { messagesBySession: next };
    }),
  removeMessage: (id) =>
    set((s) => {
      const next = { ...s.messagesBySession };
      for (const sid of Object.keys(next)) {
        next[sid] = next[sid].filter((m) => m.id !== id);
      }
      return { messagesBySession: next };
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
    set((s) => ({
      sessions: [session, ...s.sessions],
      messagesBySession: { ...s.messagesBySession, [id]: [] },
    }));
    return id;
  },
}));
