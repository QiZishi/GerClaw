import { z } from "zod";
import { GerclawApiError, gerclawRequest } from "./client";
import {
  generatedSkillSchema,
  sessionSchema,
  sessionSkillsSchema,
  skillDefinitionSchema,
  skillListSchema,
  type SkillDefinition,
  type SkillInfo,
} from "./schemas";

const deletedSchema = z.object({ deleted: z.literal(true) }).strict();
const deletedSessionSchema = z
  .object({ session_id: z.string().uuid(), deleted: z.literal(true) })
  .strict();
const SESSION_MAP_KEY = "gerclaw:backend-session-map";
// Several UI areas (skills, documents and governed forms) can initialize the
// same local session in one render. Share the in-flight request so a single
// click cannot fan out into duplicate session creation requests.
const pendingBackendSessions = new Map<string, Promise<string>>();
const sessionMapSchema = z
  .record(z.string().min(1).max(128), z.string().uuid())
  .refine(
    (value) =>
      !Object.keys(value).some((key) =>
        ["__proto__", "prototype", "constructor"].includes(key)
      ),
    "unsafe session map key"
  );

export async function listSkills(): Promise<SkillInfo[]> {
  return gerclawRequest("skills", skillListSchema);
}

export async function getSkill(skillId: string): Promise<SkillDefinition> {
  return gerclawRequest(`skills/${encodeURIComponent(skillId)}`, skillDefinitionSchema);
}

export async function registerSkill(
  sourceMarkdown: string,
  origin: "text" | "upload" | "generated" = "text"
): Promise<SkillDefinition> {
  return gerclawRequest("skills", skillDefinitionSchema, {
    method: "POST",
    body: JSON.stringify({ source_markdown: sourceMarkdown, origin }),
  });
}

export async function generateSkill(description: string): Promise<SkillDefinition> {
  const result = await gerclawRequest("skills/generate", generatedSkillSchema, {
    method: "POST",
    body: JSON.stringify({ description }),
  });
  return result.definition;
}

export async function evolveSkill(
  skill: SkillInfo,
  changeRequest: string
): Promise<SkillDefinition> {
  const result = await gerclawRequest(
    `skills/${encodeURIComponent(skill.skill_id)}/evolve`,
    generatedSkillSchema,
    {
      method: "POST",
      body: JSON.stringify({
        change_request: changeRequest,
        expected_revision: skill.revision,
      }),
    }
  );
  return result.definition;
}

export async function previewSkillUpload(file: File): Promise<SkillDefinition> {
  const body = new FormData();
  body.set("file", file);
  return gerclawRequest("skills/preview-upload", skillDefinitionSchema, {
    method: "POST",
    body,
  });
}

export async function updateSkill(
  skill: SkillInfo,
  sourceMarkdown: string
): Promise<SkillDefinition> {
  return gerclawRequest(`skills/${encodeURIComponent(skill.skill_id)}`, skillDefinitionSchema, {
    method: "PATCH",
    body: JSON.stringify({
      source_markdown: sourceMarkdown,
      expected_revision: skill.revision,
    }),
  });
}

export async function setSkillEnabled(
  skill: SkillInfo,
  enabled: boolean
): Promise<SkillDefinition> {
  return gerclawRequest(`skills/${encodeURIComponent(skill.skill_id)}`, skillDefinitionSchema, {
    method: "PATCH",
    body: JSON.stringify({ enabled, expected_revision: skill.revision }),
  });
}

export async function deleteSkill(skill: SkillInfo): Promise<void> {
  const query = new URLSearchParams({ expected_revision: String(skill.revision) });
  await gerclawRequest(
    `skills/${encodeURIComponent(skill.skill_id)}?${query}`,
    deletedSchema,
    { method: "DELETE" }
  );
}

export function backendSessionId(localSessionId: string): string {
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(localSessionId)) {
    return localSessionId;
  }
  if (typeof window === "undefined") return localSessionId;
  let current: Record<string, string> = {};
  try {
    const result = sessionMapSchema.safeParse(
      JSON.parse(window.localStorage.getItem(SESSION_MAP_KEY) ?? "{}")
    );
    if (result.success) {
      current = result.data;
    } else {
      window.localStorage.removeItem(SESSION_MAP_KEY);
    }
  } catch {
    window.localStorage.removeItem(SESSION_MAP_KEY);
    current = {};
  }
  const existing = current[localSessionId];
  if (existing) return existing;
  const created = crypto.randomUUID();
  current[localSessionId] = created;
  window.localStorage.setItem(SESSION_MAP_KEY, JSON.stringify(current));
  return created;
}

export async function ensureBackendSession(localSessionId: string): Promise<string> {
  const pending = pendingBackendSessions.get(localSessionId);
  if (pending) return pending;
  const sessionId = backendSessionId(localSessionId);
  const request = gerclawRequest("sessions", sessionSchema, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  }).then(() => sessionId);
  pendingBackendSessions.set(localSessionId, request);
  try {
    return await request;
  } finally {
    pendingBackendSessions.delete(localSessionId);
  }
}

function mappedBackendSessionId(localSessionId: string): string | null {
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(localSessionId)) {
    return localSessionId;
  }
  if (typeof window === "undefined") return null;
  try {
    const parsed = sessionMapSchema.safeParse(
      JSON.parse(window.localStorage.getItem(SESSION_MAP_KEY) ?? "{}")
    );
    return parsed.success ? parsed.data[localSessionId] ?? null : null;
  } catch {
    return null;
  }
}

function clearBackendSessionMapping(localSessionId: string): void {
  if (typeof window === "undefined") return;
  try {
    const parsed = sessionMapSchema.safeParse(
      JSON.parse(window.localStorage.getItem(SESSION_MAP_KEY) ?? "{}")
    );
    if (!parsed.success || !(localSessionId in parsed.data)) return;
    const next = { ...parsed.data };
    delete next[localSessionId];
    window.localStorage.setItem(SESSION_MAP_KEY, JSON.stringify(next));
  } catch {
    // Local cleanup is best-effort only; backend deletion remains authoritative.
  }
}

/** Delete the owner-scoped backend session before the UI removes its local copy. */
export async function deleteBackendSession(localSessionId: string): Promise<void> {
  const sessionId = mappedBackendSessionId(localSessionId);
  if (!sessionId) return;
  try {
    await gerclawRequest(`sessions/${sessionId}`, deletedSessionSchema, { method: "DELETE" });
  } catch (error) {
    // A local-only or already-deleted session has no durable data left to protect.
    if (!(error instanceof GerclawApiError) || error.code !== "CHAT_SESSION_NOT_FOUND") {
      throw error;
    }
  }
  clearBackendSessionMapping(localSessionId);
}

export async function replaceSessionSkills(
  localSessionId: string,
  skillIds: string[]
): Promise<string[]> {
  const sessionId = await ensureBackendSession(localSessionId);
  const result = await gerclawRequest(
    `skills/sessions/${sessionId}/selection`,
    sessionSkillsSchema,
    { method: "PUT", body: JSON.stringify({ skill_ids: skillIds }) }
  );
  return result.skill_ids;
}

export async function readSessionSkills(localSessionId: string): Promise<string[]> {
  const sessionId = await ensureBackendSession(localSessionId);
  const result = await gerclawRequest(
    `skills/sessions/${sessionId}/selection`,
    sessionSkillsSchema
  );
  return result.skill_ids;
}
