import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveConfig } from '../src/config.ts'

const pkg = join(import.meta.dirname, '..')
const source = (name: string) => readFile(join(pkg, name), 'utf8')

describe('dsh-talk interaction consumer', () => {
  it('keeps the 60-second recording cap without provider credentials', () => {
    expect(resolveConfig(undefined)).toMatchObject({
      sttEngine: 'qianwen',
      ttsEngine: 'qianwen',
      recordMaxSeconds: 60,
    })
    expect(() => resolveConfig({ record: { maxSeconds: 61 } })).toThrow('固定为 60 秒')
  })

  it('is a Loader-mounted consumer of the replaceable speech service', async () => {
    const [index, service, config] = await Promise.all([
      source('src/index.ts'),
      source('src/service.ts'),
      source('src/config.ts'),
    ])
    expect(index).toContain('export default TalkService')
    expect(index).not.toContain('.plugin(')
    expect(service).toContain("static inject = ['speech', 'sessions', 'sessionProjections', 'webServer']")
    expect(service).toContain('ctx.speech.acceptAsrUpgrade')
    for (const secretField of ['asrApiKey', 'ttsApiKey', 'asrUrl', 'ttsUrl'])
      expect(config).not.toContain(secretField)
  })

  it('flushes the worklet tail and cleans all client resources', async () => {
    const client = await source('src/client/TalkMicButton.tsx')
    expect(client).toContain("event.data.type !== 'flush'")
    expect(client).toContain("this.port.postMessage({ type: 'flushed' })")
    expect(client).toContain('window.clearTimeout(current.stopTimer)')
    expect(client).toContain('current.stream.getTracks().forEach')
    expect(client).toContain('await current.context.close().catch')
    expect(client).not.toContain('上传音频')
    expect(client).not.toContain('type="file"')
  })

  it('keeps audio-file decoding behind the general upload control', async () => {
    const [client, transcriber, upload] = await Promise.all([
      source('src/client/TalkMicButton.tsx'),
      source('src/client/VoiceFileTranscriber.ts'),
      readFile(join(pkg, '../client-ui/src/client/ConversationDocumentUpload.tsx'), 'utf8'),
    ])
    expect(client).not.toContain('type="file"')
    expect(client).not.toContain('上传音频')
    expect(transcriber).toContain("super(ctx, 'gerclawVoiceFiles')")
    expect(transcriber).toContain('context.decodeAudioData')
    expect(transcriber).toContain("file.type.startsWith('audio/')")
    expect(transcriber).toContain('const isAborted = (): boolean => cancelled || signal?.aborted === true')
    expect(transcriber).toContain('ctx.effect(() => () =>')
    expect(upload).toContain('audio/*')
    expect(upload).toContain('getVoiceFiles()')
    expect(upload).toContain('voiceFiles.transcribe')
    expect(upload).toContain('inputActions.submit()')
    expect(upload).not.toContain('requestAnimationFrame(() => inputActions.submit())')
  })

  it('returns the reply action to idle whenever composer input interrupts playback', async () => {
    const client = await source('src/client/TalkMessageButton.tsx')
    const mic = await source('src/client/TalkMicButton.tsx')
    expect(client).toContain("onStopped: () => { if (mounted.current) setPhase('idle') }")
    expect(client).toContain('playback.onStopped()')
    expect(client).toContain('export function interruptPlayback()')
    expect(client).toContain('active.lease = lease.current')
    expect(client).toContain('if (active?.lease === expectedLease) void stopActive()')
    expect(mic).toContain('interruptPlayback()')
    expect(mic).toContain('const actions = inputActionsRef.current')
    expect(mic).toContain('if (text && finishing.current && directSend.current) actions.submit()')
    expect(mic).toContain('onClick={() => { void finish(false) }}')
    expect(mic).toContain('onClick={() => { void finish(true) }}')
    expect(mic).not.toContain('requestAnimationFrame')
    expect(mic).not.toContain('gerclaw:voice-interrupt')
  })

  it('replaces the composer with the recording strip while capture is active', async () => {
    const [mic, styles] = await Promise.all([
      source('src/client/TalkMicButton.tsx'),
      source('src/client/styles.ts'),
    ])
    expect(mic).toContain("const recording = phase === 'connecting' || phase === 'recording' || phase === 'finishing'")
    expect(mic).toContain('data-gerclaw-recording-strip')
    expect(mic).toContain('data-gerclaw-recording-wave')
    expect(mic).toContain('data-gerclaw-recording-send')
    expect(styles).toContain('[data-composer-card]:has([data-gerclaw-recording-strip])')
  })
})
