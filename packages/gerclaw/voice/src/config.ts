/** dsh-talk interaction configuration; provider credentials live outside this plugin. */
import z from '@deepseek-ai/schemastery'

export const DEFAULT_MAX_RECORD_SECONDS = 60
export const MAX_RECORD_SECONDS = 60
export const DEFAULT_MAX_SPEAK_CHARS = 20_000
export const MAX_SPEAK_CHARS = 100_000
export const DEFAULT_MAX_AUDIO_CACHE_BYTES = 8 * 1024 * 1024
export const MAX_AUDIO_CACHE_BYTES = 64 * 1024 * 1024

export interface RecordConfig {
  enabled?: boolean
  hotkey?: string | null
  /** GerClaw intentionally caps every live/uploaded clip at 60 seconds. */
  maxSeconds?: number
}

export interface Config {
  record?: RecordConfig
  stt?: { language?: string; interim?: boolean }
  tts?: { voice?: string }
  interrupt?: boolean
  maxSpeakChars?: number
  maxAudioCacheBytes?: number
}

export interface ResolvedConfig {
  recordEnabled: boolean
  recordHotkey: string | null
  recordMaxSeconds: 60
  sttEngine: 'qianwen'
  sttLanguage: string
  sttInterim: boolean
  ttsEngine: 'qianwen'
  ttsVoice: string
  interruptEnabled: boolean
  maxSpeakChars: number
  maxAudioCacheBytes: number
}

export const Config: z<Config> = z.object({
  record: z.object({
    enabled: z.boolean().default(true),
    hotkey: z.union([z.string(), z.const(null)]).default(null),
    maxSeconds: z.const(60).default(60),
  }),
  stt: z.object({
    language: z.string().default('zh-CN'),
    interim: z.boolean().default(true),
  }),
  tts: z.object({ voice: z.string() }),
  interrupt: z.boolean().default(true),
  maxSpeakChars: z.number().min(1).max(MAX_SPEAK_CHARS).default(DEFAULT_MAX_SPEAK_CHARS),
  maxAudioCacheBytes: z.number().min(1024 * 1024).max(MAX_AUDIO_CACHE_BYTES).default(DEFAULT_MAX_AUDIO_CACHE_BYTES),
}) as unknown as z<Config>

const text = (value: unknown, fallback: string, label: string): string => {
  if (value === undefined) return fallback
  if (typeof value !== 'string' || value.trim() === '')
    throw new Error(`GerClaw 语音配置 ${label} 不能为空`)
  return value.trim()
}

const boundedNumber = (value: unknown, fallback: number, min: number, max: number, label: string): number => {
  if (value === undefined) return fallback
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max)
    throw new Error(`GerClaw 语音配置 ${label} 必须在 ${min} 到 ${max} 之间`)
  return value
}

export function resolveConfig(config: Config | undefined): ResolvedConfig {
  if (config?.record?.maxSeconds !== undefined && config.record.maxSeconds !== 60)
    throw new Error('GerClaw 语音录音时长固定为 60 秒')
  const hotkey = config?.record?.hotkey
  if (hotkey !== undefined && hotkey !== null && (typeof hotkey !== 'string' || hotkey.length > 40))
    throw new Error('GerClaw 语音快捷键不能超过 40 个字符')
  return Object.freeze({
    recordEnabled: config?.record?.enabled !== false,
    recordHotkey: hotkey ?? null,
    recordMaxSeconds: 60,
    sttEngine: 'qianwen',
    sttLanguage: text(config?.stt?.language, 'zh-CN', 'stt.language'),
    sttInterim: config?.stt?.interim !== false,
    ttsEngine: 'qianwen',
    ttsVoice: text(config?.tts?.voice, 'Cherry', 'tts.voice'),
    interruptEnabled: config?.interrupt !== false,
    maxSpeakChars: boundedNumber(config?.maxSpeakChars, DEFAULT_MAX_SPEAK_CHARS, 1, MAX_SPEAK_CHARS, 'maxSpeakChars'),
    maxAudioCacheBytes: boundedNumber(config?.maxAudioCacheBytes, DEFAULT_MAX_AUDIO_CACHE_BYTES, 1024 * 1024, MAX_AUDIO_CACHE_BYTES, 'maxAudioCacheBytes'),
  })
}
