import { z } from "zod";

const identitySchema = z.object({
  actor_id: z.string().regex(/^usr_account_[a-f0-9]{32}$/),
  role: z.enum(["patient", "doctor"]),
}).strict();
const statusSchema = z.discriminatedUnion("authenticated", [
  z.object({ authenticated: z.literal(false) }).strict(),
  identitySchema.extend({ authenticated: z.literal(true) }).strict(),
]);

const sessionSchema = identitySchema.extend({
  expires_in: z.number().int().min(300).max(86_400),
}).strict();

export type AccountIdentity = z.infer<typeof identitySchema>;
type AccountRole = AccountIdentity["role"];

function csrfToken(): string | null {
  return document.cookie.split("; ").find((item) => item.startsWith("gerclaw_account_csrf="))?.split("=")[1] ?? null;
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

export async function getAccountIdentity(): Promise<AccountIdentity | null> {
  try {
    const response = await fetch("/api/account/status", { cache: "no-store" });
    const parsed = statusSchema.safeParse(await readJson(response));
    if (!response.ok || !parsed.success || !parsed.data.authenticated) return null;
    return { actor_id: parsed.data.actor_id, role: parsed.data.role };
  } catch {
    // Session discovery must never turn a usable visitor page into an unhandled
    // client error if the local BFF is restarting.
    return null;
  }
}

async function startAccountSession(
  action: "login" | "register",
  payload: { username: string; password: string; role?: AccountRole },
): Promise<AccountIdentity> {
  const response = await fetch(`/api/account/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const parsed = sessionSchema.safeParse(await readJson(response));
  if (!response.ok || !parsed.success) throw new Error("ACCOUNT_REQUEST_FAILED");
  return { actor_id: parsed.data.actor_id, role: parsed.data.role };
}

export function loginAccount(username: string, password: string): Promise<AccountIdentity> {
  return startAccountSession("login", { username, password });
}

export function registerAccount(
  username: string,
  password: string,
  role: AccountRole,
): Promise<AccountIdentity> {
  return startAccountSession("register", { username, password, role });
}

export async function logoutAccount(): Promise<void> {
  const csrf = csrfToken();
  if (!csrf) throw new Error("ACCOUNT_SESSION_INVALID");
  const response = await fetch("/api/account/logout", {
    method: "POST",
    headers: { "x-gerclaw-csrf": csrf },
  });
  if (!response.ok && response.status !== 401) throw new Error("ACCOUNT_REQUEST_FAILED");
}

export async function deactivateAccount(currentPassword: string): Promise<void> {
  const csrf = csrfToken();
  if (!csrf) throw new Error("ACCOUNT_SESSION_INVALID");
  const response = await fetch("/api/account/deactivate", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-gerclaw-csrf": csrf },
    body: JSON.stringify({ current_password: currentPassword }),
  });
  if (!response.ok) throw new Error(response.status === 401 ? "ACCOUNT_PASSWORD_INVALID" : "ACCOUNT_REQUEST_FAILED");
}
