import { createHmac } from "node:crypto";
import { z } from "zod";

import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const GUEST_ACCESS_COOKIE = "gerclaw_guest_token";
export const ACCOUNT_ACCESS_COOKIE = "gerclaw_account_access";
export const VISITOR_ID_COOKIE = "gerclaw_visitor_id";

const visitorIdSchema = z.string().regex(/^[a-f0-9]{32}$/);
const guestTokenSchema = z
  .object({
    access_token: z.string().min(32),
    expires_in: z.number().int().min(300).max(86_400),
  })
  .passthrough();

interface GuestCredential {
  accessToken: string;
  expiresIn: number;
}

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
  return createHmac("sha256", secret)
    .update(`gerclaw-guest-bootstrap:v1:${visitorId}`)
    .digest("hex");
}

async function issueGuestCredential(apiBase: string, visitorId: string): Promise<GuestCredential> {
  const response = await fetch(`${apiBase}/api/v1/auth/guest`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "X-GerClaw-Visitor-ID": visitorId,
      "X-GerClaw-Visitor-Signature": visitorSignature(visitorId),
    },
    cache: "no-store",
  });
  if (!response.ok) throw new Error("访客身份服务暂时不可用");

  const parsed = guestTokenSchema.safeParse(await response.json().catch(() => null));
  if (!parsed.success) throw new Error("访客身份响应格式不正确");
  return { accessToken: parsed.data.access_token, expiresIn: parsed.data.expires_in };
}

/**
 * Resolve the same HttpOnly account/guest identity used by the BFF proxy.
 * This is intentionally server-only: callers receive no bearer token and may
 * only attach the resulting cookies to their own same-origin response.
 */
export async function resolveGerclawAccess(
  request: Request,
  options: { refreshGuest?: boolean } = {}
): Promise<GerclawAccess> {
  const apiBase = getGerclawApiBaseUrl();
  const cookieHeader = request.headers.get("cookie") ?? "";
  const accountAccessToken = readCookie(cookieHeader, ACCOUNT_ACCESS_COOKIE);
  const cookieVisitorId = visitorIdSchema.safeParse(readCookie(cookieHeader, VISITOR_ID_COOKIE));
  const headerVisitorId = visitorIdSchema.safeParse(request.headers.get("x-gerclaw-visitor-id"));

  if (accountAccessToken) {
    return { accessToken: accountAccessToken, applyCookies: () => undefined };
  }

  const visitorId = cookieVisitorId.success
    ? cookieVisitorId.data
    : headerVisitorId.success
      ? headerVisitorId.data
      : null;
  if (!visitorId) throw new Error("访客身份尚未初始化，请刷新后重试");

  const visitorCookieRequired = !cookieVisitorId.success;
  let credential: GuestCredential | null = null;
  let accessToken =
    options.refreshGuest || visitorCookieRequired
      ? undefined
      : readCookie(cookieHeader, GUEST_ACCESS_COOKIE);
  if (!accessToken) {
    credential = await issueGuestCredential(apiBase, visitorId);
    accessToken = credential.accessToken;
  }

  return {
    accessToken,
    applyCookies(response: Response) {
      if (credential) {
        response.headers.append(
          "Set-Cookie",
          `${GUEST_ACCESS_COOKIE}=${encodeURIComponent(credential.accessToken)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${credential.expiresIn}${process.env.NODE_ENV === "production" ? "; Secure" : ""}`
        );
      }
      if (visitorCookieRequired) {
        response.headers.append(
          "Set-Cookie",
          `${VISITOR_ID_COOKIE}=${visitorId}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000${process.env.NODE_ENV === "production" ? "; Secure" : ""}`
        );
      }
    },
  };
}
