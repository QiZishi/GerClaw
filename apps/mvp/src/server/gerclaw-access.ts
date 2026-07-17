import { createHmac, randomUUID } from "node:crypto";
import { z } from "zod";

import { getGerclawApiBaseUrl } from "./gerclaw-api.ts";

export const ACCOUNT_ACCESS_COOKIE = "gerclaw_account_access";
export const GUEST_ACCESS_COOKIE = "gerclaw_guest_token";
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
  const cookieHeader = request.headers.get("cookie") ?? "";
  const accountAccessToken = readCookie(cookieHeader, ACCOUNT_ACCESS_COOKIE);
  if (accountAccessToken) return { accessToken: accountAccessToken, applyCookies: () => undefined };
  // A guest starts from the mandatory login page, but all BFF calls made in
  // that browser session must share one server-issued patient-only identity.
  // This is deliberately a session cookie: closing the browser removes it, so
  // a later guest entry cannot restore the prior guest's chat history.
  const guestAccessToken = readCookie(cookieHeader, GUEST_ACCESS_COOKIE);
  if (guestAccessToken) return { accessToken: guestAccessToken, applyCookies: () => undefined };
  const visitorId = randomUUID().replaceAll("-", "");
  const credential = await issueGuestCredential(visitorId);
  return {
    accessToken: credential.accessToken,
    applyCookies(response: Response) {
      response.headers.append("Set-Cookie", `${GUEST_ACCESS_COOKIE}=${encodeURIComponent(credential.accessToken)}; Path=/; HttpOnly; SameSite=Lax${process.env.NODE_ENV === "production" ? "; Secure" : ""}`);
    },
  };
}
