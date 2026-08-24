/** Qianwen-only GerClaw voice configuration. */
import z from '@deepseek-ai/schemastery'

export const QIANWEN_ASR_MODEL = 'qwen3-asr-flash-realtime'
export const QIANWEN_TTS_MODEL = 'qwen3-tts-instruct-flash-realtime'
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
  /** Final Qianwen ASR text is submitted automatically. */
  autoSubmit?: boolean
}

export interface Config {
  asrApiKey?: string
  asrUrl?: string
  ttsApiKey?: string
  ttsUrl?: string
  asrModel?: string
  ttsModel?: string
  ttsVoice?: string
  ttsInstructions?: string
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
  recordAutoSubmit: true
  sttEngine: 'qianwen'
  sttLanguage: string
  sttInterim: boolean
  asrModel: typeof QIANWEN_ASR_MODEL
  ttsEngine: 'qianwen'
  ttsModel: typeof QIANWEN_TTS_MODEL
  ttsVoice: string
  interruptEnabled: boolean
  maxSpeakChars: number
  maxAudioCacheBytes: number
}

export const Config: z<Config> = z.object({
  asrApiKey: z.string(),
  asrUrl: z.string(),
  ttsApiKey: z.string(),
  ttsUrl: z.string(),
  asrModel: z.string(),
  ttsModel: z.string(),
  ttsVoice: z.string(),
  ttsInstructions: z.string(),
  record: z.object({
    enabled: z.boolean().default(true),
    hotkey: z.union([z.string(), z.const(null)]).default(null),
    maxSeconds: z.const(60).default(60),
    autoSubmit: z.const(true).default(true),
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
  const asrModel = text(config?.asrModel, '', 'ASR_MODEL')
  const ttsModel = text(config?.ttsModel, '', 'TTS_MODEL')
  if (asrModel !== QIANWEN_ASR_MODEL)
    throw new Error(`GerClaw 语音仅支持 ASR_MODEL=${QIANWEN_ASR_MODEL}`)
  if (ttsModel !== QIANWEN_TTS_MODEL)
    throw new Error(`GerClaw 语音仅支持 TTS_MODEL=${QIANWEN_TTS_MODEL}`)
  for (const [label, value] of [
    ['MODEL_ASR_KEY', config?.asrApiKey],
    ['MODEL_ASR_URL', config?.asrUrl],
    ['MODEL_TTS_KEY', config?.ttsApiKey],
    ['MODEL_TTS_URL', config?.ttsUrl],
  ] as const) text(value, '', label)
  if (config?.record?.maxSeconds !== undefined && config.record.maxSeconds !== 60)
    throw new Error('GerClaw 语音录音时长固定为 60 秒')
  if (config?.record?.autoSubmit !== undefined && config.record.autoSubmit !== true)
    throw new Error('GerClaw 语音最终转写必须自动发送')
  const hotkey = config?.record?.hotkey
  if (hotkey !== undefined && hotkey !== null && (typeof hotkey !== 'string' || hotkey.length > 40))
    throw new Error('GerClaw 语音快捷键不能超过 40 个字符')
  return Object.freeze({
    recordEnabled: config?.record?.enabled !== false,
    recordHotkey: hotkey ?? null,
    recordMaxSeconds: 60,
    recordAutoSubmit: true,
    sttEngine: 'qianwen',
    sttLanguage: text(config?.stt?.language, 'zh-CN', 'stt.language'),
    sttInterim: config?.stt?.interim !== false,
    asrModel: QIANWEN_ASR_MODEL,
    ttsEngine: 'qianwen',
    ttsModel: QIANWEN_TTS_MODEL,
    ttsVoice: text(config?.tts?.voice ?? config?.ttsVoice, 'Cherry', 'tts.voice'),
    interruptEnabled: config?.interrupt !== false,
    maxSpeakChars: boundedNumber(config?.maxSpeakChars, DEFAULT_MAX_SPEAK_CHARS, 1, MAX_SPEAK_CHARS, 'maxSpeakChars'),
    maxAudioCacheBytes: boundedNumber(config?.maxAudioCacheBytes, DEFAULT_MAX_AUDIO_CACHE_BYTES, 1024 * 1024, MAX_AUDIO_CACHE_BYTES, 'maxAudioCacheBytes'),
  })
}
