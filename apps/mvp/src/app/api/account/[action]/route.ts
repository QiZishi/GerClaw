import { randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { accountSessionSchema } from "@/server/account-contract";
import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ACCESS_COOKIE = "gerclaw_account_access";
const REFRESH_COOKIE = "gerclaw_account_refresh";
const CSRF_COOKIE = "gerclaw_account_csrf";
const actionSchema = z.enum(["register", "login", "refresh", "logout", "password", "deactivate", "switch-view"]);
const accountStatusSchema = z.object({
  actor_id: z.string().regex(/^usr_account_[a-f0-9]{32}$/),
  role: z.enum(["patient", "doctor", "admin"]),
  account_role: z.enum(["patient", "doctor", "admin"]),
}).strict();
const accountName = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{2,47}$/);

const registerSchema = z.object({
  username: accountName,
  password: z.string().min(12).max(128),
  role: z.enum(["patient", "doctor"]),
}).strict();
const loginSchema = registerSchema.pick({ username: true, password: true });
const passwordSchema = z.object({
  current_password: z.string().min(1).max(128),
  new_password: z.string().min(12).max(128),
}).strict();
const deactivationSchema = z.object({
  current_password: z.string().min(1).max(128),
}).strict();
const switchViewSchema = z.object({ role: z.enum(["patient", "doctor"]) }).strict();

function cookieOptions(maxAge: number, httpOnly: boolean) {
  return {
    httpOnly,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}

function csrfIsValid(request: NextRequest): boolean {
  const expected = request.cookies.get(CSRF_COOKIE)?.value;
  const received = request.headers.get("x-gerclaw-csrf");
  return Boolean(expected && received && expected === received);
}

function sessionResponse(session: z.infer<typeof accountSessionSchema>): NextResponse {
  const response = NextResponse.json({
    actor_id: session.actor_id,
    role: session.role,
    account_role: session.account_role,
    expires_in: session.expires_in,
  });
  response.cookies.set(ACCESS_COOKIE, session.access_token, cookieOptions(session.expires_in, true));
  response.cookies.set(REFRESH_COOKIE, session.refresh_token, cookieOptions(2_592_000, true));
  response.cookies.set(CSRF_COOKIE, randomBytes(32).toString("hex"), cookieOptions(2_592_000, false));
  return response;
}

function clearSession(response: NextResponse) {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE]) {
    response.cookies.set(name, "", { ...cookieOptions(0, name !== CSRF_COOKIE), maxAge: 0 });
  }
}

export async function POST(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  const action = actionSchema.safeParse((await context.params).action);
  if (!action.success) return NextResponse.json({ error: { code: "ACCOUNT_ACTION_INVALID" } }, { status: 404 });
  if (["refresh", "logout", "password", "deactivate", "switch-view"].includes(action.data) && !csrfIsValid(request)) {
    return NextResponse.json({ error: { code: "CSRF_INVALID" } }, { status: 403 });
  }

  let apiBase: string;
  try { apiBase = getGerclawApiBaseUrl(); } catch {
    return NextResponse.json({ error: { code: "API_NOT_CONFIGURED" } }, { status: 503 });
  }
  const raw = await request.json().catch(() => null);
  let body: object;
  if (action.data === "register") {
    const parsed = registerSchema.safeParse(raw); if (!parsed.success) return NextResponse.json({ error: { code: "ACCOUNT_INPUT_INVALID" } }, { status: 422 }); body = parsed.data;
  } else if (action.data === "login") {
    const parsed = loginSchema.safeParse(raw); if (!parsed.success) return NextResponse.json({ error: { code: "ACCOUNT_INPUT_INVALID" } }, { status: 422 }); body = parsed.data;
  } else if (action.data === "password") {
    const parsed = passwordSchema.safeParse(raw); if (!parsed.success) return NextResponse.json({ error: { code: "ACCOUNT_INPUT_INVALID" } }, { status: 422 }); body = parsed.data;
  } else if (action.data === "deactivate") {
    const parsed = deactivationSchema.safeParse(raw); if (!parsed.success) return NextResponse.json({ error: { code: "ACCOUNT_INPUT_INVALID" } }, { status: 422 }); body = parsed.data;
  } else if (action.data === "switch-view") {
    const parsed = switchViewSchema.safeParse(raw); if (!parsed.success) return NextResponse.json({ error: { code: "ACCOUNT_INPUT_INVALID" } }, { status: 422 }); body = parsed.data;
  } else {
    const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
    if (!refresh) return NextResponse.json({ error: { code: "ACCOUNT_SESSION_REQUIRED" } }, { status: 401 });
    body = { refresh_token: refresh };
  }
  const headers: Record<string, string> = { "Content-Type": "application/json", Accept: "application/json" };
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  if (["password", "deactivate", "switch-view"].includes(action.data) && access) headers.Authorization = `Bearer ${access}`;
  const upstream = await fetch(`${apiBase}/api/v1/auth/${action.data}`, { method: "POST", headers, body: JSON.stringify(body), cache: "no-store" });
  if (action.data === "logout" && upstream.status === 204) { const response = new NextResponse(null, { status: 204 }); clearSession(response); return response; }
  if (!upstream.ok) return NextResponse.json({ error: { code: "ACCOUNT_REQUEST_FAILED" } }, { status: upstream.status });
  if (["password", "deactivate"].includes(action.data)) { const response = new NextResponse(null, { status: 204 }); clearSession(response); return response; }
  const session = accountSessionSchema.safeParse(await upstream.json().catch(() => null));
  if (!session.success) return NextResponse.json({ error: { code: "ACCOUNT_RESPONSE_INVALID" } }, { status: 502 });
  return sessionResponse(session.data);
}

export async function GET(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  const { action } = await context.params;
  // `status` deliberately reuses this dynamic segment without expanding the
  // mutation allowlist. It has no user-controlled body or cookies exposed.
  if (action !== "status") {
    return NextResponse.json({ error: { code: "ACCOUNT_ACTION_INVALID" } }, { status: 404 });
  }
  let apiBase: string;
  try { apiBase = getGerclawApiBaseUrl(); } catch {
    return NextResponse.json({ error: { code: "API_NOT_CONFIGURED" } }, { status: 503 });
  }
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!access) return NextResponse.json({ authenticated: false }, { headers: { "Cache-Control": "no-store" } });
  const upstream = await fetch(`${apiBase}/api/v1/auth/session`, {
    headers: { Authorization: `Bearer ${access}`, Accept: "application/json" },
    cache: "no-store",
  });
  if (upstream.status === 401 || upstream.status === 403) {
    return NextResponse.json({ authenticated: false }, { headers: { "Cache-Control": "no-store" } });
  }
  if (!upstream.ok) return NextResponse.json({ error: { code: "ACCOUNT_SESSION_INVALID" } }, { status: upstream.status });
  const identity = accountStatusSchema.safeParse(await upstream.json().catch(() => null));
  if (!identity.success) return NextResponse.json({ error: { code: "ACCOUNT_RESPONSE_INVALID" } }, { status: 502 });
  return NextResponse.json({ authenticated: true, ...identity.data }, { headers: { "Cache-Control": "no-store" } });
}
