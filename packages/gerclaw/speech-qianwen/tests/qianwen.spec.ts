import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  QIANWEN_ASR_MODEL,
  QIANWEN_TTS_MODEL,
} from '@gerclaw/speech'
import {
  MAX_ASR_AUDIO_BYTES,
  MAX_TTS_SEGMENT_CHARS,
  splitTtsText,
} from '../src/index.ts'

const pkg = join(import.meta.dirname, '..')
const source = (name: string) => readFile(join(pkg, name), 'utf8')
describe('Qianwen-only configuration', () => {
  it('fixes the two official models and the 60-second PCM limit', () => {
    expect(QIANWEN_ASR_MODEL).toBe('qwen3-asr-flash-realtime')
    expect(QIANWEN_TTS_MODEL).toBe('qwen3-tts-instruct-flash-realtime')
    expect(MAX_ASR_AUDIO_BYTES).toBe(1_920_000)
  })

  it('has no legacy provider or runtime fallback in compiled source surfaces', async () => {
    const texts = await Promise.all(['src/index.ts'].map(source))
    const joined = texts.join('\n')
    for (const legacy of ["'edge-tts'", "'piper'", "'whisper'", "'funasr'", "'browser'"])
      expect(joined).not.toContain(legacy)
    expect(joined).not.toContain('fallbackToBrowser')
    expect(joined).not.toContain('SILICONFLOW_')
  })

  it('publishes the SpeechProvider service without mounting a consumer', async () => {
    const index = await source('src/index.ts')
    expect(index).toContain('extends SpeechProvider')
    expect(index).not.toContain('.plugin(')
    expect(index).not.toContain('registerUpgrade(')
  })
})

describe('Qianwen realtime protocol', () => {
  it('uses manual ASR commit and official TTS streaming events', async () => {
    const qianwen = await source('src/index.ts')
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

})
