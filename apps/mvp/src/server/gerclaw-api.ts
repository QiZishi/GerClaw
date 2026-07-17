import { z } from "zod";

const apiUrlSchema = z
  .string()
  .url()
  .transform((value) => value.replace(/\/+$/, ""));
const uuidPattern = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";

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
    pattern: /^skills\/[a-z][a-z0-9_.-]{1,63}\/evolve$/,
    methods: new Set(["POST"]),
  },
  {
    pattern: /^skills\/sessions\/[0-9a-f-]{36}\/selection$/,
    methods: new Set(["GET", "PUT"]),
  },
  { pattern: /^sessions$/, methods: new Set(["POST"]) },
  {
    pattern: new RegExp(`^sessions/${uuidPattern}/messages$`, "i"),
    methods: new Set(["GET"]),
  },
  {
    pattern: new RegExp(`^sessions/${uuidPattern}$`, "i"),
    methods: new Set(["DELETE"]),
  },
  { pattern: /^chat$/, methods: new Set(["POST"]) },
  { pattern: /^voice\/(?:asr|tts)$/, methods: new Set(["POST"]) },
  { pattern: /^documents$/, methods: new Set(["POST"]) },
  {
    pattern: new RegExp(`^documents/sessions/${uuidPattern}/${uuidPattern}$`, "i"),
    methods: new Set(["GET", "DELETE"]),
  },
  { pattern: /^cga\/scales$/, methods: new Set(["GET"]) },
  { pattern: /^cga\/assessments$/, methods: new Set(["GET", "POST"]) },
  { pattern: /^cga\/assessments\/active$/, methods: new Set(["GET"]) },
  {
    pattern: new RegExp(`^cga/assessments/${uuidPattern}$`, "i"),
    methods: new Set(["GET"]),
  },
  { pattern: new RegExp(`^cga/assessments/${uuidPattern}/(?:answers|complete)$`, "i"), methods: new Set(["POST"]) },
  { pattern: new RegExp(`^cga/assessments/${uuidPattern}/report$`, "i"), methods: new Set(["GET"]) },
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
  { pattern: /^clinical-intakes$/, methods: new Set(["POST"]) },
  {
    pattern: new RegExp(`^clinical-intakes/${uuidPattern}$`, "i"),
    methods: new Set(["GET", "PATCH"]),
  },
  {
    pattern: new RegExp(`^clinical-intakes/${uuidPattern}/medication-reconciliation$`, "i"),
    methods: new Set(["GET"]),
  },
  { pattern: /^memory\/profile$/, methods: new Set(["GET"]) },
  {
    pattern: new RegExp(`^memory/facts/${uuidPattern}/decision$`, "i"),
    methods: new Set(["POST"]),
  },
  { pattern: /^chronic-care\/conditions$/, methods: new Set(["GET", "POST"]) },
  { pattern: /^risk-alerts$/, methods: new Set(["GET"]) },
  {
    pattern: new RegExp(`^risk-alerts/${uuidPattern}/acknowledgements$`, "i"),
    methods: new Set(["POST"]),
  },
  {
    pattern: new RegExp(`^chronic-care/conditions/${uuidPattern}/measurements$`, "i"),
    methods: new Set(["GET", "POST"]),
  },
  {
    pattern: new RegExp(`^chronic-care/conditions/${uuidPattern}/trends$`, "i"),
    methods: new Set(["GET"]),
  },
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
