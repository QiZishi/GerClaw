import { createServer, type Server } from 'node:http'
import { once } from 'node:events'
import { Context, Service } from '@deepseek-ai/cordis'
import { describe, expect, it, afterEach } from 'vitest'
import WebSocket, { WebSocketServer } from 'ws'
import { QIANWEN_ASR_MODEL, QIANWEN_TTS_MODEL } from '@gerclaw/speech'
import { QianwenSpeechProvider } from '../src/index.ts'

const pcm = (size = 3_200): Buffer => Buffer.alloc(size, 7)

const textOf = (raw: WebSocket.RawData): string => {
  if (typeof raw === 'string') return raw
  if (Buffer.isBuffer(raw)) return raw.toString('utf8')
  if (Array.isArray(raw)) return Buffer.concat(raw).toString('utf8')
  return Buffer.from(new Uint8Array(raw)).toString('utf8')
}

type Fixture = {
  http: Server
  upstream: WebSocketServer
  provider: QianwenSpeechProvider
  context: Context
  port: number
}

const fixtures: Fixture[] = []

const closeFixture = async (fixture: Fixture): Promise<void> => {
  const init = (fixture.provider as unknown as Record<PropertyKey, unknown>)[Service.init]
  if (typeof init === 'function') {
    (init as (this: QianwenSpeechProvider) => void).call(fixture.provider)
  }
  await fixture.context.fiber.dispose()
  for (const client of fixture.upstream.clients) client.terminate()
  await new Promise<void>((resolve) => { fixture.upstream.close(() => { resolve() }) })
  await new Promise<void>((resolve) => { fixture.http.close(() => { resolve() }) })
}

afterEach(async () => {
  while (fixtures.length) await closeFixture(fixtures.pop()!)
})

const makeFixture = async (onUpstream: (socket: WebSocket) => void): Promise<Fixture> => {
  const http = createServer()
  const upstream = new WebSocketServer({ noServer: true })
  upstream.on('connection', onUpstream)
  http.on('upgrade', (req, socket, head) => {
    if (req.url?.startsWith('/qwen')) {
      upstream.handleUpgrade(req, socket, head, (client) => { upstream.emit('connection', client, req) })
      return
    }
    // The ASR browser-side upgrade is attached by the individual test after
    // the HTTP server has accepted the connection. Other paths are ignored.
  })
  http.listen(0, '127.0.0.1')
  await once(http, 'listening')
  const address = http.address()
  if (address === null || typeof address === 'string') throw new Error('test server did not bind')
  const context = new Context()
  const provider = new QianwenSpeechProvider(context, {
    asrApiKey: 'test-asr-key',
    asrUrl: `ws://127.0.0.1:${address.port}/qwen`,
    ttsApiKey: 'test-tts-key',
    ttsUrl: `ws://127.0.0.1:${address.port}/qwen`,
    asrModel: QIANWEN_ASR_MODEL,
    ttsModel: QIANWEN_TTS_MODEL,
    ttsVoice: 'Cherry',
  })
  const fixture = { http, upstream, provider, context, port: address.port }
  fixtures.push(fixture)
  return fixture
}

describe('Qianwen realtime protocol and cleanup', () => {
  it('streams manual PCM ASR interim/final events and closes the upstream socket', async () => {
    let upstreamClosed = false
    const fixture = await makeFixture((socket) => {
      socket.once('close', () => { upstreamClosed = true })
      socket.on('message', (raw) => {
        const event = JSON.parse(textOf(raw)) as { type?: string }
        if (event.type === 'session.update') socket.send(JSON.stringify({ type: 'session.updated' }))
        if (event.type === 'input_audio_buffer.commit') {
          socket.send(JSON.stringify({ type: 'conversation.item.input_audio_transcription.text', text: '你好' }))
          socket.send(JSON.stringify({ type: 'conversation.item.input_audio_transcription.completed', transcript: '你好' }))
          socket.send(JSON.stringify({ type: 'session.finished' }))
        }
      })
      socket.send(JSON.stringify({ type: 'session.created' }))
    })
    const browser = new WebSocket(`ws://127.0.0.1:${fixture.port}/asr`)
    const events: Array<{ type?: string; text?: string }> = []
    const persisted: string[] = []
    browser.on('message', (raw) => { events.push(JSON.parse(textOf(raw)) as { type?: string; text?: string }) })
    await new Promise<void>((resolve, reject) => {
      fixture.http.once('upgrade', (req, socket, head) => {
        fixture.provider.acceptAsrUpgrade(req, socket, head, (event) => { persisted.push(event.status) })
        resolve()
      })
      browser.once('error', reject)
    })
    if (browser.readyState !== WebSocket.OPEN) await once(browser, 'open')
    await new Promise<void>((resolve) => {
      const check = () => {
        if (events.some(event => event.type === 'ready')) resolve()
        else setTimeout(check, 5)
      }
      check()
    })
    browser.send(pcm())
    browser.send(JSON.stringify({ type: 'commit' }))
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => { reject(new Error('ASR test timed out')) }, 2_000)
      const check = () => {
        if (events.some(event => event.type === 'done')) {
          clearTimeout(timer)
          resolve()
        } else setTimeout(check, 5)
      }
      check()
    })
    expect(events).toEqual(expect.arrayContaining([
      { type: 'partial', text: '你好' },
      expect.objectContaining({ type: 'final', text: '你好' }),
      { type: 'done' },
    ]))
    expect(persisted).toEqual(['completed'])
    if (browser.readyState !== WebSocket.CLOSED) await once(browser, 'close')
    await new Promise<void>((resolve) => {
      const check = () => {
        if (upstreamClosed) resolve()
        else setTimeout(check, 5)
      }
      check()
    })
  })

  it('streams 24 kHz PCM TTS and aborts the upstream connection', async () => {
    let receivedFinish = false
    let upstreamClosed = false
    const fixture = await makeFixture((socket) => {
      socket.once('close', () => { upstreamClosed = true })
      socket.on('message', (raw) => {
        const event = JSON.parse(textOf(raw)) as { type?: string }
        if (event.type === 'session.update') socket.send(JSON.stringify({ type: 'session.updated' }))
        if (event.type === 'input_text_buffer.commit') {
          socket.send(JSON.stringify({ type: 'response.audio.delta', delta: Buffer.from(pcm(4)).toString('base64') }))
        }
        if (event.type === 'session.finish') {
          receivedFinish = true
          socket.send(JSON.stringify({ type: 'session.finished' }))
        }
      })
      socket.send(JSON.stringify({ type: 'session.created' }))
    })
    const chunks: Uint8Array[] = []
    for await (const chunk of fixture.provider.synthesizeStream('请读出这句话')) chunks.push(chunk.audio)
    expect(Buffer.concat(chunks.map(chunk => Buffer.from(chunk)))).toEqual(pcm(4))
    expect(receivedFinish).toBe(true)
    const abort = new AbortController()
    const stream = fixture.provider.synthesizeStream('请停止朗读', abort.signal)
    const first = stream.next()
    abort.abort('user-cancelled')
    await expect(first).rejects.toMatchObject({ name: 'AbortError' })
    await new Promise<void>((resolve) => {
      const check = () => {
        if (upstreamClosed) resolve()
        else setTimeout(check, 5)
      }
      check()
    })
  })
})
