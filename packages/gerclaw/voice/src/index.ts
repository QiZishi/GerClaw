/** MiMo/SiliconFlow ASR and 24 kHz mono PCM16LE TTS provider. */
import { Context, Service } from '@deepseek-ai/cordis'
export type AudioFormat = 'wav' | 'mp3' | 'webm'
export interface VoiceConfig {
  mimoApiKey?: string
  mimoAsrUrl?: string
  mimoTtsUrl?: string
  siliconFlowApiKey?: string
  siliconFlowUrl?: string
  asrModel?: string
  ttsModel?: string
  ttsVoice?: string
}
export interface VoiceAsrResult {
  schemaVersion: 'voice-asr-response-v1'
  text: string
  elapsedMs: number
}
export interface VoiceTtsResult {
  schemaVersion: 'voice-tts-pcm16-v1'
  audio: Uint8Array
  sampleRate: 24000
  channels: 1
  encoding: 'pcm16le'
  elapsedMs: number
}
const DEFAULT_STYLE = '用温柔体贴的语调，语速适中，像在关心一位老人的健康状况'
const DEFAULT_VOICE = '冰糖'
const collectSse = async (
  response: Response,
  kind: 'text' | 'audio',
): Promise<string | Uint8Array> => {
  if (!response.ok) throw new Error(`语音服务暂时不可用（${response.status}）`)
  const body = await response.text()
  const fragments: string[] = []
  const chunks: Uint8Array[] = []
  for (const line of body.split(/\r?\n/)) {
    if (!line.startsWith('data:')) continue
    const payload = line.slice(5).trim()
    if (!payload || payload === '[DONE]') continue
    let parsed: {
      choices?: Array<{
        delta?: { content?: string; audio?: { data?: string } }
      }>
      error?: { message?: string }
    }
    try {
      parsed = JSON.parse(payload) as typeof parsed
    } catch {
      throw new Error('语音服务返回了无法识别的数据')
    }
    if (parsed.error) throw new Error('语音服务拒绝了本次请求')
    for (const choice of parsed.choices ?? []) {
      if (kind === 'text' && choice.delta?.content)
        fragments.push(choice.delta.content)
      const encoded = choice.delta?.audio?.data
      if (kind === 'audio' && encoded)
        chunks.push(Buffer.from(encoded, 'base64'))
    }
  }
  if (kind === 'text') {
    const text = fragments.join('').trim()
    if (!text) throw new Error('没有识别出可用语音')
    return text
  }
  if (chunks.length === 0) throw new Error('语音服务没有返回音频')
  const audio = Buffer.concat(chunks)
  if (audio.length % 2 !== 0) throw new Error('语音服务返回的 PCM 音频无效')
  return audio
}
export class VoiceService extends Service {
  private readonly config: VoiceConfig
  constructor(ctx: Context, config: VoiceConfig = {}) {
    super(ctx, 'gerclawVoice')
    this.config = config
  }
  missingForAsr(): string[] {
    return ['MIMO_API_KEY', 'MIMO_ASR_URL', 'ASR_MODEL'].filter(
      name =>
        !(
          {
            MIMO_API_KEY: this.config.mimoApiKey,
            MIMO_ASR_URL: this.config.mimoAsrUrl,
            ASR_MODEL: this.config.asrModel,
          } as Record<string, string | undefined>
        )[name],
    )
  }
  missingForTts(): string[] {
    const hasMimo = Boolean(
      this.config.mimoApiKey && this.config.mimoTtsUrl && this.config.ttsModel,
    )
    const hasSf = Boolean(
      this.config.siliconFlowApiKey &&
        this.config.siliconFlowUrl &&
        this.config.ttsModel,
    )
    return hasMimo || hasSf
      ? []
      : [
        'MIMO_API_KEY/MIMO_TTS_URL 或 SILICONFLOW_API_KEY/SILICONFLOW_URL',
        'TTS_MODEL',
      ]
  }
  async transcribe(
    audio: Uint8Array,
    format: AudioFormat,
    signal?: AbortSignal,
  ): Promise<VoiceAsrResult> {
    const missing = this.missingForAsr()
    if (missing.length) throw new Error(`缺少环境变量：${missing.join('、')}`)
    if (audio.length === 0 || audio.length > 8 * 1024 * 1024)
      throw new Error('录音大小必须在 1 字节到 8 MB 之间')
    const started = performance.now()
    const asrUrl = this.config.mimoAsrUrl ?? ''
    const apiKey = this.config.mimoApiKey ?? ''
    const response = await fetch(
      `${asrUrl.replace(/\/$/, '')}/chat/completions`,
      {
        method: 'POST',
        ...(signal === undefined ? {} : { signal }),
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: this.config.asrModel,
          messages: [
            {
              role: 'user',
              content: [
                {
                  type: 'input_audio',
                  input_audio: {
                    data: Buffer.from(audio).toString('base64'),
                    format,
                  },
                },
              ],
            },
          ],
          stream: true,
        }),
      },
    )
    const text = (await collectSse(response, 'text')) as string
    return {
      schemaVersion: 'voice-asr-response-v1',
      text: text.slice(0, 4000),
      elapsedMs: Math.round(performance.now() - started),
    }
  }
  async synthesize(
    text: string,
    style: string = DEFAULT_STYLE,
    signal?: AbortSignal,
  ): Promise<VoiceTtsResult> {
    const missing = this.missingForTts()
    if (missing.length) throw new Error(`缺少环境变量：${missing.join('、')}`)
    const cleaned = text.trim().slice(0, 8000)
    if (!cleaned) throw new Error('语音回复内容不能为空')
    const started = performance.now()
    let audio: Uint8Array
    if (this.config.mimoApiKey && this.config.mimoTtsUrl) {
      const response = await fetch(
        `${this.config.mimoTtsUrl.replace(/\/$/, '')}/chat/completions`,
        {
          method: 'POST',
          ...(signal === undefined ? {} : { signal }),
          headers: {
            Authorization: `Bearer ${this.config.mimoApiKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: this.config.ttsModel,
            messages: [
              { role: 'user', content: style.slice(0, 300) },
              { role: 'assistant', content: cleaned },
            ],
            audio: {
              format: 'pcm16',
              voice: this.config.ttsVoice ?? DEFAULT_VOICE,
            },
            stream: true,
          }),
        },
      )
      audio = (await collectSse(response, 'audio')) as Uint8Array
    } else {
      const siliconFlowUrl = this.config.siliconFlowUrl ?? ''
      const siliconFlowApiKey = this.config.siliconFlowApiKey ?? ''
      const response = await fetch(
        `${siliconFlowUrl.replace(/\/$/, '')}/audio/speech`,
        {
          method: 'POST',
          ...(signal === undefined ? {} : { signal }),
          headers: {
            Authorization: `Bearer ${siliconFlowApiKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: this.config.ttsModel,
            input: cleaned,
            response_format: 'pcm',
            sample_rate: 24000,
          }),
        },
      )
      if (!response.ok)
        throw new Error(`语音服务暂时不可用（${response.status}）`)
      audio = new Uint8Array(await response.arrayBuffer())
      if (audio.length === 0 || audio.length % 2 !== 0)
        throw new Error('语音服务返回的 PCM 音频无效')
    }
    return {
      schemaVersion: 'voice-tts-pcm16-v1',
      audio,
      sampleRate: 24000,
      channels: 1,
      encoding: 'pcm16le',
      elapsedMs: Math.round(performance.now() - started),
    }
  }
}
declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawVoice: VoiceService
  }
}
export default VoiceService
