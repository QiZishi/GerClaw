import { create } from "zustand";
import {
  deleteSkill as deleteRemoteSkill,
  evolveSkill,
  generateSkill,
  getSkill,
  listSkills,
  previewSkillUpload,
  registerSkill,
  setSkillEnabled,
  updateSkill,
} from "@/services/gerclaw/skills";
import type {
  SkillDefinition,
  SkillDraft,
  SkillEvolution,
  SkillInfo,
  SkillMutation,
} from "@/services/gerclaw/schemas";

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
  ) => Promise<SkillMutation>;
  update: (skill: SkillInfo, markdown: string) => Promise<SkillMutation>;
  generateDraft: (description: string) => Promise<SkillDraft>;
  evolveDraft: (skill: SkillInfo, changeRequest: string) => Promise<SkillEvolution>;
  inspectUpload: (file: File) => Promise<SkillDefinition>;
  toggle: (skill: SkillInfo, enabled: boolean) => Promise<SkillDefinition>;
  remove: (skill: SkillInfo) => Promise<void>;
}

function upsert(skills: SkillInfo[], item: SkillInfo): SkillInfo[] {
  const existing = skills.findIndex((skill) => skill.skill_id === item.skill_id);
  if (existing === -1) return [...skills, item];
  return skills.map((skill) => (skill.skill_id === item.skill_id ? item : skill));
}

function activeMutationDefinition(
  mutation: SkillMutation
): SkillDefinition | null {
  if ("decision" in mutation) return mutation.active_definition;
  return mutation;
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
    const mutation = await registerSkill(markdown, origin);
    const active = activeMutationDefinition(mutation);
    if (active) {
      set((state) => ({ skills: upsert(state.skills, active), status: "ready" }));
    }
    return mutation;
  },
  update: async (skill, markdown) => {
    const mutation = await updateSkill(skill, markdown);
    const active = activeMutationDefinition(mutation);
    if (active) {
      set((state) => ({ skills: upsert(state.skills, active), status: "ready" }));
    }
    return mutation;
  },
  generateDraft: (description) => generateSkill(description),
  evolveDraft: async (skill, changeRequest) => {
    const outcome = await evolveSkill(skill, changeRequest);
    if (outcome.active_definition) {
      set((state) => ({
        skills: upsert(state.skills, outcome.active_definition as SkillDefinition),
        status: "ready",
      }));
    }
    return outcome;
  },
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
