import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  QIANWEN_ASR_MODEL,
  QIANWEN_TTS_MODEL,
  resolveConfig,
} from '../src/config.ts'
import {
  MAX_ASR_AUDIO_BYTES,
  MAX_TTS_SEGMENT_CHARS,
  splitTtsText,
} from '../src/qianwen.ts'

const pkg = join(import.meta.dirname, '..')
const source = (name: string) => readFile(join(pkg, name), 'utf8')
const validConfig = {
  asrApiKey: 'test-asr-key',
  asrUrl: 'wss://example.invalid/asr',
  ttsApiKey: 'test-tts-key',
  ttsUrl: 'wss://example.invalid/tts',
  asrModel: QIANWEN_ASR_MODEL,
  ttsModel: QIANWEN_TTS_MODEL,
} as const

describe('Qianwen-only configuration', () => {
  it('fixes the two official models and 60-second auto-submit policy', () => {
    expect(resolveConfig(validConfig)).toMatchObject({
      sttEngine: 'qianwen',
      asrModel: QIANWEN_ASR_MODEL,
      ttsEngine: 'qianwen',
      ttsModel: QIANWEN_TTS_MODEL,
      recordMaxSeconds: 60,
      recordAutoSubmit: true,
    })
    expect(MAX_ASR_AUDIO_BYTES).toBe(1_920_000)
  })

  it('rejects alternative models and relaxed recording policies', () => {
    expect(() => resolveConfig({ ...validConfig, asrModel: 'another-asr' })).toThrow('仅支持 ASR_MODEL')
    expect(() => resolveConfig({ ...validConfig, ttsModel: 'another-tts' })).toThrow('仅支持 TTS_MODEL')
    expect(() => resolveConfig({ ...validConfig, record: { maxSeconds: 61 } })).toThrow('固定为 60 秒')
    expect(() => resolveConfig({ ...validConfig, record: { autoSubmit: false } })).toThrow('必须自动发送')
  })

  it('has no legacy provider or runtime fallback in compiled source surfaces', async () => {
    const texts = await Promise.all([
      'src/config.ts',
      'src/service.ts',
      'src/wire.ts',
      'src/client/remote.ts',
    ].map(source))
    const joined = texts.join('\n')
    for (const legacy of ["'edge-tts'", "'piper'", "'whisper'", "'funasr'", "'browser'"])
      expect(joined).not.toContain(legacy)
    expect(joined).not.toContain('fallbackToBrowser')
    expect(joined).not.toContain('SILICONFLOW_')
  })

  it('mounts TalkService through Cordis so its Qianwen dependency is injected', async () => {
    const index = await source('src/index.ts')
    expect(index).toContain('await ctx.plugin(TalkService, resolved)')
    expect(index).not.toContain('new TalkService(')
  })
})

describe('Qianwen realtime protocol', () => {
  it('uses manual ASR commit and official TTS streaming events', async () => {
    const qianwen = await source('src/qianwen.ts')
    for (const event of [
      'session.update',
      'input_audio_buffer.append',
      'input_audio_buffer.commit',
      'conversation.item.input_audio_transcription.text',
      'conversation.item.input_audio_transcription.completed',
      'input_text_buffer.append',
      'input_text_buffer.commit',
      'response.audio.delta',
      'session.finish',
    ]) expect(qianwen).toContain(event)
    expect(qianwen).toContain('turn_detection: null')
    expect(qianwen).toContain('sample_rate: 16000')
    expect(qianwen).toContain('sample_rate: 24000')
  })

  it('splits long text on sentence boundaries without losing content', () => {
    const text = `${'甲'.repeat(MAX_TTS_SEGMENT_CHARS - 2)}。${'乙'.repeat(1_500)}！最后一句。`
    const segments = splitTtsText(text)
    expect(segments.length).toBeGreaterThan(2)
    expect(segments.every(segment => segment.length <= MAX_TTS_SEGMENT_CHARS)).toBe(true)
    expect(segments.join('')).toBe(text)
  })

  it('flushes the worklet tail and cleans all client resources', async () => {
    const client = await source('src/client/TalkMicButton.tsx')
    expect(client).toContain("event.data.type !== 'flush'")
    expect(client).toContain("this.port.postMessage({ type: 'flushed' })")
    expect(client).toContain('window.clearTimeout(current.stopTimer)')
    expect(client).toContain('current.stream.getTracks().forEach')
    expect(client).toContain('await current.context.close().catch')
    expect(client).toContain("throw new Error('音频不能超过 60 秒')")
  })

  it('returns the reply action to idle whenever composer input interrupts playback', async () => {
    const client = await source('src/client/TalkMessageButton.tsx')
    expect(client).toContain("onStopped: () => { if (mounted.current) setPhase('idle') }")
    expect(client).toContain('playback.onStopped()')
    expect(client).toContain('active.lease = lease.current')
    expect(client).toContain('if (active?.lease === expectedLease) void stopActive()')
  })
})
