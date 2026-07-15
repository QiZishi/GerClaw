import { z } from "zod";

const apiUrlSchema = z
  .string()
  .url()
  .transform((value) => value.replace(/\/+$/, ""));

const proxyRules: Array<{ pattern: RegExp; methods: ReadonlySet<string> }> = [
  {
    pattern: /^skills(?:\/[a-z][a-z0-9_.-]{1,63})?(?:\/execute)?$/,
    methods: new Set(["GET", "POST", "PATCH", "DELETE"]),
  },
  {
    pattern: /^skills\/(?:upload|preview-upload|generate)$/,
    methods: new Set(["POST"]),
  },
  {
    pattern: /^skills\/sessions\/[0-9a-f-]{36}\/selection$/,
    methods: new Set(["GET", "PUT"]),
  },
  {
    pattern: /^sessions(?:\/[0-9a-f-]{36}\/messages)?$/,
    methods: new Set(["GET", "POST"]),
  },
  { pattern: /^chat$/, methods: new Set(["POST"]) },
  {
    pattern: /^runtime\/approvals\/[0-9a-f-]{36}(?:\/(?:cancel|decision|review))?$/,
    methods: new Set(["GET", "POST"]),
  },
  {
    pattern: /^chat\/trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}\/cancel$/,
    methods: new Set(["POST"]),
  },
  { pattern: /^traces\/[A-Za-z0-9_.-]{3,64}$/, methods: new Set(["GET"]) },
  { pattern: /^feedback$/, methods: new Set(["POST"]) },
];

export function getGerclawApiBaseUrl(): string {
  const parsed = apiUrlSchema.safeParse(process.env.GERCLAW_API_URL);
  if (!parsed.success) {
    throw new Error("GERCLAW_API_URL 未配置或格式不正确");
  }
  const url = new URL(parsed.data);
  if (url.username || url.password) {
    throw new Error("GERCLAW_API_URL 不得包含凭证");
  }
  return parsed.data;
}

export function isAllowedGerclawProxyTarget(path: string, method: string): boolean {
  if (!path || path.includes("..") || path.includes("//")) return false;
  return proxyRules.some((rule) => rule.pattern.test(path) && rule.methods.has(method));
}
