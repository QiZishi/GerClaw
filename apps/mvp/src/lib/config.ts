/**
 * 环境变量加载与 Zod 校验
 * 对齐 gerclaw设计要求.md §4.5 配置管理 / §15.1 安全约束 / FRONTEND.md §8
 * 所有外部 API Key/模型名/URL 通过 NEXT_PUBLIC_ 环境变量配置，禁止硬编码
 */
import { z } from "zod";

const envSchema = z.object({
  NEXT_PUBLIC_PRIMARY_URL: z.string().default(""),
  NEXT_PUBLIC_PRIMARY_API_KEY: z.string().default(""),
  NEXT_PUBLIC_PRIMARY_MODEL: z.string().default("gpt-4o"),
  NEXT_PUBLIC_PRIMARY_PROTOCOL: z
    .enum(["openai", "dashscope", "anthropic"])
    .default("openai"),

  NEXT_PUBLIC_BACKUP1_URL: z.string().default(""),
  NEXT_PUBLIC_BACKUP1_API_KEY: z.string().default(""),
  NEXT_PUBLIC_BACKUP1_MODEL: z.string().default("qwen-plus"),
  NEXT_PUBLIC_BACKUP1_PROTOCOL: z
    .enum(["openai", "dashscope", "anthropic"])
    .default("openai"),

  NEXT_PUBLIC_BACKUP2_URL: z.string().default(""),
  NEXT_PUBLIC_BACKUP2_API_KEY: z.string().default(""),
  NEXT_PUBLIC_BACKUP2_MODEL: z.string().default("claude-sonnet-4-20250514"),
  NEXT_PUBLIC_BACKUP2_PROTOCOL: z
    .enum(["openai", "dashscope", "anthropic"])
    .default("anthropic"),

  NEXT_PUBLIC_ASR_URL: z.string().default(""),
  NEXT_PUBLIC_ASR_API_KEY: z.string().default(""),
  NEXT_PUBLIC_ASR_MODEL: z.string().default("mimo-v2.5-asr"),
  NEXT_PUBLIC_TTS_URL: z.string().default(""),
  NEXT_PUBLIC_TTS_API_KEY: z.string().default(""),
  NEXT_PUBLIC_TTS_MODEL: z.string().default("mimo-v2.5-tts"),
  NEXT_PUBLIC_TTS_VOICE: z.string().default("冰糖"),

  NEXT_PUBLIC_ANYSEARCH_API_KEY: z.string().default(""),
  NEXT_PUBLIC_TAVILY_API_KEY: z.string().default(""),

  NEXT_PUBLIC_MINERU_URL: z.string().default(""),
  NEXT_PUBLIC_MINERU_API_KEY: z.string().default(""),

  NEXT_PUBLIC_APP_NAME: z.string().default("GerClaw"),
  NEXT_PUBLIC_APP_VERSION: z.string().default("0.1.0"),
});

export type EnvConfig = z.infer<typeof envSchema>;

function loadEnv(): EnvConfig {
  const parsed = envSchema.safeParse(process.env);
  if (!parsed.success) {
    if (process.env.NODE_ENV === "development") {
      console.warn("[config] 环境变量校验警告：", parsed.error.format());
    }
    return envSchema.parse({});
  }

  const data = parsed.data;

  if (process.env.NODE_ENV === "development") {
    if (!data.NEXT_PUBLIC_PRIMARY_URL || !data.NEXT_PUBLIC_PRIMARY_API_KEY) {
      console.warn(
        "[config] ⚠️ 主模型未配置：NEXT_PUBLIC_PRIMARY_URL 或 NEXT_PUBLIC_PRIMARY_API_KEY 为空，LLM 功能将不可用。请在 .env.local 中配置。"
      );
    }
  }

  return data;
}

export const env = loadEnv();

export const primaryModel = {
  url: env.NEXT_PUBLIC_PRIMARY_URL,
  apiKey: env.NEXT_PUBLIC_PRIMARY_API_KEY,
  modelName: env.NEXT_PUBLIC_PRIMARY_MODEL,
  protocol: env.NEXT_PUBLIC_PRIMARY_PROTOCOL,
  preference: "primary" as const,
};

export const backup1Model = {
  url: env.NEXT_PUBLIC_BACKUP1_URL,
  apiKey: env.NEXT_PUBLIC_BACKUP1_API_KEY,
  modelName: env.NEXT_PUBLIC_BACKUP1_MODEL,
  protocol: env.NEXT_PUBLIC_BACKUP1_PROTOCOL,
  preference: "backup1" as const,
};

export const backup2Model = {
  url: env.NEXT_PUBLIC_BACKUP2_URL,
  apiKey: env.NEXT_PUBLIC_BACKUP2_API_KEY,
  modelName: env.NEXT_PUBLIC_BACKUP2_MODEL,
  protocol: env.NEXT_PUBLIC_BACKUP2_PROTOCOL,
  preference: "backup2" as const,
};

export const voiceConfig = {
  asrUrl: env.NEXT_PUBLIC_ASR_URL,
  asrApiKey: env.NEXT_PUBLIC_ASR_API_KEY,
  asrModel: env.NEXT_PUBLIC_ASR_MODEL,
  ttsUrl: env.NEXT_PUBLIC_TTS_URL,
  ttsApiKey: env.NEXT_PUBLIC_TTS_API_KEY,
  ttsModel: env.NEXT_PUBLIC_TTS_MODEL,
  ttsVoice: env.NEXT_PUBLIC_TTS_VOICE,
};

export const searchConfig = {
  anysearchApiKey: env.NEXT_PUBLIC_ANYSEARCH_API_KEY,
  tavilyApiKey: env.NEXT_PUBLIC_TAVILY_API_KEY,
};

export const documentConfig = {
  mineruUrl: env.NEXT_PUBLIC_MINERU_URL,
  mineruApiKey: env.NEXT_PUBLIC_MINERU_API_KEY,
};

export function hasRealLLMConfig(): boolean {
  return Boolean(primaryModel.apiKey && primaryModel.url);
}

export function hasRealVoiceConfig(): boolean {
  return Boolean(
    voiceConfig.asrApiKey && voiceConfig.asrUrl && voiceConfig.ttsUrl
  );
}

export function hasRealSearchConfig(): boolean {
  return Boolean(searchConfig.anysearchApiKey || searchConfig.tavilyApiKey);
}
