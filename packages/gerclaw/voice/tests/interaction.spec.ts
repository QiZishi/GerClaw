import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveConfig } from '../src/config.ts'

const pkg = join(import.meta.dirname, '..')
const source = (name: string) => readFile(join(pkg, name), 'utf8')

describe('dsh-talk interaction consumer', () => {
  it('keeps the 60-second auto-submit policy without provider credentials', () => {
    expect(resolveConfig(undefined)).toMatchObject({
      sttEngine: 'qianwen',
      ttsEngine: 'qianwen',
      recordMaxSeconds: 60,
      recordAutoSubmit: true,
    })
    expect(() => resolveConfig({ record: { maxSeconds: 61 } })).toThrow('固定为 60 秒')
    expect(() => resolveConfig({ record: { autoSubmit: false } })).toThrow('必须自动发送')
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
