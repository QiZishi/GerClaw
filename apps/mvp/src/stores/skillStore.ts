import { create } from "zustand";
import {
  deleteSkill as deleteRemoteSkill,
  generateSkill,
  getSkill,
  listSkills,
  previewSkillUpload,
  registerSkill,
  setSkillEnabled,
  updateSkill,
} from "@/services/gerclaw/skills";
import type { SkillDefinition, SkillInfo } from "@/services/gerclaw/schemas";

type SkillStatus = "idle" | "loading" | "ready" | "error";

interface SkillState {
  skills: SkillInfo[];
  status: SkillStatus;
  error: string | null;
  refresh: () => Promise<void>;
  load: (skillId: string) => Promise<SkillDefinition>;
  create: (
    markdown: string,
    origin?: "text" | "upload" | "generated"
  ) => Promise<SkillDefinition>;
  update: (skill: SkillInfo, markdown: string) => Promise<SkillDefinition>;
  generateDraft: (description: string) => Promise<SkillDefinition>;
  inspectUpload: (file: File) => Promise<SkillDefinition>;
  toggle: (skill: SkillInfo, enabled: boolean) => Promise<SkillDefinition>;
  remove: (skill: SkillInfo) => Promise<void>;
}

function upsert(skills: SkillInfo[], item: SkillInfo): SkillInfo[] {
  const existing = skills.findIndex((skill) => skill.skill_id === item.skill_id);
  if (existing === -1) return [...skills, item];
  return skills.map((skill) => (skill.skill_id === item.skill_id ? item : skill));
}

export const useSkillStore = create<SkillState>()((set, get) => ({
  skills: [],
  status: "idle",
  error: null,
  refresh: async () => {
    if (get().status === "loading") return;
    set({ status: "loading", error: null });
    try {
      set({ skills: await listSkills(), status: "ready" });
    } catch (error) {
      set({
        status: "error",
        error: error instanceof Error ? error.message : "技能列表加载失败",
      });
    }
  },
  load: (skillId) => getSkill(skillId),
  create: async (markdown, origin = "text") => {
    const definition = await registerSkill(markdown, origin);
    set((state) => ({ skills: upsert(state.skills, definition), status: "ready" }));
    return definition;
  },
  update: async (skill, markdown) => {
    const definition = await updateSkill(skill, markdown);
    set((state) => ({ skills: upsert(state.skills, definition), status: "ready" }));
    return definition;
  },
  generateDraft: (description) => generateSkill(description),
  inspectUpload: (file) => previewSkillUpload(file),
  toggle: async (skill, enabled) => {
    const definition = await setSkillEnabled(skill, enabled);
    set((state) => ({ skills: upsert(state.skills, definition) }));
    return definition;
  },
  remove: async (skill) => {
    await deleteRemoteSkill(skill);
    set((state) => ({
      skills: state.skills.filter((item) => item.skill_id !== skill.skill_id),
    }));
  },
}));
