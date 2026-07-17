import { createHmac, randomUUID } from "node:crypto";
import { z } from "zod";

import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const ACCOUNT_ACCESS_COOKIE = "gerclaw_account_access";
export const GUEST_ACCESS_COOKIE = "gerclaw_guest_token";
export const VISITOR_ID_COOKIE = "gerclaw_visitor_id";
const visitorIdSchema = z.string().regex(/^[a-f0-9]{32}$/);
const guestTokenSchema = z.object({ access_token: z.string().min(32), expires_in: z.number().int().min(300).max(86_400) }).passthrough();

export interface GerclawAccess {
  accessToken: string;
  applyCookies(response: Response): void;
}

function readCookie(cookieHeader: string, name: string): string | undefined {
  const match = new RegExp(`(?:^|;\\s*)${name}=([^;]*)`).exec(cookieHeader);
  return match?.[1];
}

export function hasGerclawAccountAccess(request: Request): boolean {
  return Boolean(readCookie(request.headers.get("cookie") ?? "", ACCOUNT_ACCESS_COOKIE));
}

function visitorSignature(visitorId: string): string {
  const secret = z.string().min(32).parse(process.env.GERCLAW_GUEST_IDENTITY_SECRET);
  return createHmac("sha256", secret).update(`gerclaw-guest-bootstrap:v1:${visitorId}`).digest("hex");
}

async function issueGuestCredential(visitorId: string): Promise<{ accessToken: string; expiresIn: number }> {
  const response = await fetch(`${getGerclawApiBaseUrl()}/api/v1/auth/guest`, { method: "POST", headers: { Accept: "application/json", "X-GerClaw-Visitor-ID": visitorId, "X-GerClaw-Visitor-Signature": visitorSignature(visitorId) }, cache: "no-store" });
  const parsed = guestTokenSchema.safeParse(await response.json().catch(() => null));
  if (!response.ok || !parsed.success) throw new Error("GUEST_IDENTITY_UNAVAILABLE");
  return { accessToken: parsed.data.access_token, expiresIn: parsed.data.expires_in };
}

/** Resolve account identity or a bounded, patient-only guest identity. */
export async function resolveGerclawAccess(
  request: Request,
  _options: { refreshGuest?: boolean } = {},
): Promise<GerclawAccess> {
  void _options;
  const accountAccessToken = readCookie(request.headers.get("cookie") ?? "", ACCOUNT_ACCESS_COOKIE);
  if (accountAccessToken) return { accessToken: accountAccessToken, applyCookies: () => undefined };
  const cookieHeader = request.headers.get("cookie") ?? "";
  const visitor = visitorIdSchema.safeParse(readCookie(cookieHeader, VISITOR_ID_COOKIE) ?? request.headers.get("x-gerclaw-visitor-id"));
  const visitorId = visitor.success ? visitor.data : randomUUID().replaceAll("-", "");
  const credential = await issueGuestCredential(visitorId);
  return {
    accessToken: credential.accessToken,
    applyCookies(response: Response) {
      response.headers.append("Set-Cookie", `${GUEST_ACCESS_COOKIE}=${encodeURIComponent(credential.accessToken)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${credential.expiresIn}${process.env.NODE_ENV === "production" ? "; Secure" : ""}`);
      response.headers.append("Set-Cookie", `${VISITOR_ID_COOKIE}=${visitorId}; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${process.env.NODE_ENV === "production" ? "; Secure" : ""}`);
    },
  };
}
