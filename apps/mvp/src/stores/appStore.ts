/**
 * 应用状态 store
 * 对齐 gerclaw设计要求.md §3.1 三栏布局 / §3.5 右侧动态面板 / §13.7 适老化
 * 管理：侧边栏折叠/右侧面板/角色/老年模式/主题
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ChatActionType, Citation, FileTag, RightPanelType, Role, Theme } from "@/types";
import { LAYOUT } from "@/lib/constants";
import { STORAGE_KEYS } from "@/lib/storage";

interface AppState {
  // === 主题 ===
  theme: Theme;
  setTheme: (theme: Theme) => void;

  // === 角色 ===
  role: Role;
  setRole: (role: Role) => void;

  // === 老年模式（仅患者端，默认开启）===
  seniorMode: boolean;
  setSeniorMode: (senior: boolean) => void;
  toggleSeniorMode: () => void;
  /** 患者老年模式下，完成的 AI 回复是否自动开始朗读。 */
  autoTtsPlayback: boolean;
  setAutoTtsPlayback: (enabled: boolean) => void;

  // === 侧边栏折叠 ===
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  /** 移动端侧边栏抽屉 */
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;

  // === 右侧动态面板 ===
  rightPanelOpen: boolean;
  rightPanelType: RightPanelType;
  rightPanelWidth: number;
  setRightPanel: (type: RightPanelType, open?: boolean) => void;
  closeRightPanel: () => void;
  setRightPanelWidth: (width: number) => void;

  // === 当前会话 ===
  currentSessionId: string | null;
  setCurrentSession: (id: string | null) => void;

  // === 中间栏视图（聊天 / 技能管理）===
  // 对齐 Trae Work：点击技能管理在中间栏显示，而非右侧面板
  mainView: "chat" | "skills";
  setMainView: (view: "chat" | "skills") => void;

  // === 聊天中加载的功能动作（在中间栏消息流末尾渲染对应组件）===
  chatAction: ChatActionType;
  setChatAction: (action: ChatActionType) => void;

  // === 右侧面板 Markdown 内容（用于 LLM 流式输出报告）===
  panelContent: string;
  setPanelContent: (content: string) => void;

  // === 当前引用列表（点击角标时设置，右侧面板显示）===
  currentCitations: Citation[];
  setCurrentCitations: (citations: Citation[]) => void;

  // === 输入框上下文（标签区域）===
  loadedSkillIds: string[];
  uploadedFileIds: string[];
  parsedFiles: Record<string, FileTag>;
  setLoadedSkills: (ids: string[]) => void;
  addLoadedSkill: (id: string) => void;
  removeLoadedSkill: (id: string) => void;
  addUploadedFile: (id: string) => void;
  removeUploadedFile: (id: string) => void;
  addParsedFile: (file: FileTag) => void;
  removeParsedFile: (id: string) => void;
  clearParsedFiles: () => void;
  clearInputContext: () => void;

  // === 网络状态 ===
  isOnline: boolean;
  setIsOnline: (online: boolean) => void;

  // === 服务可用性 ===
  asrAvailable: boolean;
  ttsAvailable: boolean;
  setAsrAvailable: (available: boolean) => void;
  setTtsAvailable: (available: boolean) => void;

  // === 存储警告 ===
  storageFull: boolean;
  setStorageFull: (full: boolean) => void;

  // === 流式中断提示 ===
  streamingInterrupted: boolean;
  interruptedMessageId: string | null;
  setStreamingInterrupted: (interrupted: boolean, messageId?: string | null) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // === 主题 ===
      theme: "system",
      setTheme: (theme) => set({ theme }),

      // === 角色 ===
      role: "visitor",
      setRole: (role) =>
        set({
          role,
          seniorMode: role === "patient" ? true : false,
          currentSessionId: null,
          mainView: "chat",
          chatAction: "none",
          rightPanelOpen: false,
          rightPanelType: null,
          panelContent: "",
          streamingInterrupted: false,
          interruptedMessageId: null,
        }),

      // === 老年模式 ===
      seniorMode: false,
      setSeniorMode: (seniorMode) => set({ seniorMode }),
      toggleSeniorMode: () =>
        set({ seniorMode: !get().seniorMode }),
      autoTtsPlayback: true,
      setAutoTtsPlayback: (autoTtsPlayback) => set({ autoTtsPlayback }),

      // === 侧边栏 ===
      sidebarCollapsed: false,
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () =>
        set({ sidebarCollapsed: !get().sidebarCollapsed }),
      mobileSidebarOpen: false,
      setMobileSidebarOpen: (mobileSidebarOpen) => set({ mobileSidebarOpen }),

      // === 右侧面板 ===
      rightPanelOpen: false,
      rightPanelType: null,
      rightPanelWidth: LAYOUT.rightPanel.default,
      setRightPanel: (type, open = true) =>
        set({
          rightPanelType: type,
          rightPanelOpen: open && type !== null,
          panelContent: "",
        }),
      closeRightPanel: () =>
        set({ rightPanelOpen: false, rightPanelType: null }),
      setRightPanelWidth: (width) => {
        const maxWidth = typeof window !== "undefined"
          ? Math.min(LAYOUT.rightPanel.max, Math.floor(window.innerWidth * 0.8))
          : LAYOUT.rightPanel.max;
        set({
          rightPanelWidth: Math.max(
            LAYOUT.rightPanel.min,
            Math.min(maxWidth, width)
          ),
        });
      },

      // === 当前会话 ===
      currentSessionId: null,
      setCurrentSession: (id) => set({ currentSessionId: id, chatAction: "none" }),

      // === 中间栏视图 ===
      mainView: "chat",
      setMainView: (mainView) => set({ mainView }),

      // === 聊天中加载的功能动作 ===
      chatAction: "none",
      setChatAction: (chatAction) => set({ chatAction, panelContent: "" }),

      // === 右侧面板内容 ===
      panelContent: "",
      setPanelContent: (content) => set({ panelContent: content }),

      // === 当前引用列表 ===
      currentCitations: [],
      setCurrentCitations: (citations) => set({ currentCitations: citations }),

      // === 输入框上下文 ===
      loadedSkillIds: [],
      uploadedFileIds: [],
      parsedFiles: {},
      setLoadedSkills: (loadedSkillIds) => set({ loadedSkillIds }),
      addLoadedSkill: (id) =>
        set((s) => ({
          loadedSkillIds: s.loadedSkillIds.includes(id)
            ? s.loadedSkillIds
            : [...s.loadedSkillIds, id],
        })),
      removeLoadedSkill: (id) =>
        set((s) => ({
          loadedSkillIds: s.loadedSkillIds.filter((s) => s !== id),
        })),
      addUploadedFile: (id) =>
        set((s) => ({
          uploadedFileIds: s.uploadedFileIds.includes(id)
            ? s.uploadedFileIds
            : [...s.uploadedFileIds, id],
        })),
      removeUploadedFile: (id) =>
        set((s) => ({
          uploadedFileIds: s.uploadedFileIds.filter((f) => f !== id),
        })),
      addParsedFile: (file) =>
        set((s) => ({
          parsedFiles: { ...s.parsedFiles, [file.id]: file },
        })),
      removeParsedFile: (id) =>
        set((s) => {
          const newParsedFiles = { ...s.parsedFiles };
          delete newParsedFiles[id];
          return { parsedFiles: newParsedFiles };
        }),
      clearParsedFiles: () => set({ parsedFiles: {} }),
      clearInputContext: () =>
        set({ loadedSkillIds: [], uploadedFileIds: [], parsedFiles: {} }),

      // === 网络状态 ===
      isOnline: true,
      setIsOnline: (isOnline) => set({ isOnline }),

      // === 服务可用性 ===
      asrAvailable: true,
      ttsAvailable: true,
      setAsrAvailable: (asrAvailable) => set({ asrAvailable }),
      setTtsAvailable: (ttsAvailable) => set({ ttsAvailable }),

      // === 存储警告 ===
      storageFull: false,
      setStorageFull: (storageFull) => set({ storageFull }),

      // === 流式中断提示 ===
      streamingInterrupted: false,
      interruptedMessageId: null,
      setStreamingInterrupted: (streamingInterrupted, interruptedMessageId = null) =>
        set({ streamingInterrupted, interruptedMessageId }),
    }),
    {
      name: "gerclaw:app-store",
      partialize: (state) => ({
        theme: state.theme,
        role: state.role,
        seniorMode: state.seniorMode,
        autoTtsPlayback: state.autoTtsPlayback,
        sidebarCollapsed: state.sidebarCollapsed,
        rightPanelWidth: state.rightPanelWidth,
      }),
    }
  )
);

// 兼容 storage key 常量引用
void STORAGE_KEYS;
