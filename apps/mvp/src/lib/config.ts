/**
 * 环境变量加载与 Zod 校验
 * 对齐 gerclaw设计要求.md §4.5 配置管理 / §15.1 安全约束 / FRONTEND.md §8
 * 所有外部 API Key/模型名/URL 通过 NEXT_PUBLIC_ 环境变量配置，禁止硬编码
 */
import { z } from "zod";

const envSchema = z.object({
  // === 主模型（OpenAI 兼容）===
  NEXT_PUBLIC_PRIMARY_URL: z.string().default(""),
  NEXT_PUBLIC_PRIMARY_API_KEY: z.string().default(""),
  NEXT_PUBLIC_PRIMARY_MODEL: z.string().default("gpt-4o"),
  NEXT_PUBLIC_PRIMARY_PROTOCOL: z
    .enum(["openai", "dashscope", "anthropic"])
    .default("openai"),

  // === 备份模型1（DashScope 兼容）===
  NEXT_PUBLIC_BACKUP1_URL: z.string().default(""),
  NEXT_PUBLIC_BACKUP1_API_KEY: z.string().default(""),
  NEXT_PUBLIC_BACKUP1_MODEL: z.string().default("qwen-plus"),
  NEXT_PUBLIC_BACKUP1_PROTOCOL: z
    .enum(["openai", "dashscope", "anthropic"])
    .default("openai"),

  // === 备份模型2（Anthropic 兼容）===
  NEXT_PUBLIC_BACKUP2_URL: z.string().default(""),
  NEXT_PUBLIC_BACKUP2_API_KEY: z.string().default(""),
  NEXT_PUBLIC_BACKUP2_MODEL: z.string().default("claude-sonnet-4-20250514"),
  NEXT_PUBLIC_BACKUP2_PROTOCOL: z
    .enum(["openai", "dashscope", "anthropic"])
    .default("anthropic"),

  // === Mimo 语音服务 ===
  NEXT_PUBLIC_MIMO_API_KEY: z.string().default(""),
  NEXT_PUBLIC_ASR_MODEL: z.string().default("mimo-v2.5-asr"),
  NEXT_PUBLIC_TTS_MODEL: z.string().default("mimo-v2.5-tts"),
  NEXT_PUBLIC_TTS_VOICE: z.string().default("冰糖"),

  // === 联网搜索 ===
  NEXT_PUBLIC_ANYSEARCH_API_KEY: z.string().default(""),
  NEXT_PUBLIC_TAVILY_API_KEY: z.string().default(""),

  // === MinerU 文档解析 ===
  NEXT_PUBLIC_MINERU_URL: z.string().default(""),
  NEXT_PUBLIC_MINERU_API_KEY: z.string().default(""),
});

export type EnvConfig = z.infer<typeof envSchema>;

/** 解析环境变量，缺失时使用默认值（不抛错，UI 壳子阶段允许空值） */
function loadEnv(): EnvConfig {
  const parsed = envSchema.safeParse(process.env);
  if (!parsed.success) {
    // 开发期打印警告，但不阻塞启动（UI 壳子阶段使用 mock 数据）
    if (process.env.NODE_ENV === "development") {
      console.warn("[config] 环境变量校验警告：", parsed.error.format());
    }
    return envSchema.parse({});
  }
  return parsed.data;
}

export const env = loadEnv();

/** 主模型配置 */
export const primaryModel = {
  url: env.NEXT_PUBLIC_PRIMARY_URL,
  apiKey: env.NEXT_PUBLIC_PRIMARY_API_KEY,
  modelName: env.NEXT_PUBLIC_PRIMARY_MODEL,
  protocol: env.NEXT_PUBLIC_PRIMARY_PROTOCOL,
  preference: "primary" as const,
};

/** 备份模型1 */
export const backup1Model = {
  url: env.NEXT_PUBLIC_BACKUP1_URL,
  apiKey: env.NEXT_PUBLIC_BACKUP1_API_KEY,
  modelName: env.NEXT_PUBLIC_BACKUP1_MODEL,
  protocol: env.NEXT_PUBLIC_BACKUP1_PROTOCOL,
  preference: "backup1" as const,
};

/** 备份模型2 */
export const backup2Model = {
  url: env.NEXT_PUBLIC_BACKUP2_URL,
  apiKey: env.NEXT_PUBLIC_BACKUP2_API_KEY,
  modelName: env.NEXT_PUBLIC_BACKUP2_MODEL,
  protocol: env.NEXT_PUBLIC_BACKUP2_PROTOCOL,
  preference: "backup2" as const,
};

/** 语音服务配置 */
export const voiceConfig = {
  mimoApiKey: env.NEXT_PUBLIC_MIMO_API_KEY,
  asrModel: env.NEXT_PUBLIC_ASR_MODEL,
  ttsModel: env.NEXT_PUBLIC_TTS_MODEL,
  ttsVoice: env.NEXT_PUBLIC_TTS_VOICE,
};

/** 搜索服务配置 */
export const searchConfig = {
  anysearchApiKey: env.NEXT_PUBLIC_ANYSEARCH_API_KEY,
  tavilyApiKey: env.NEXT_PUBLIC_TAVILY_API_KEY,
};

/** 文档解析配置 */
export const documentConfig = {
  mineruUrl: env.NEXT_PUBLIC_MINERU_URL,
  mineruApiKey: env.NEXT_PUBLIC_MINERU_API_KEY,
};

/** 是否已配置真实 API Key（用于 UI 提示是否走 mock） */
export function hasRealLLMConfig(): boolean {
  return Boolean(primaryModel.apiKey && primaryModel.url);
}

export function hasRealVoiceConfig(): boolean {
  return Boolean(voiceConfig.mimoApiKey);
}

export function hasRealSearchConfig(): boolean {
  return Boolean(searchConfig.anysearchApiKey || searchConfig.tavilyApiKey);
}
