import process from 'node:process'
import { createInterface } from 'node:readline'
import { once } from 'node:events'

const rows = await new Promise((resolve, reject) => {
  const collected = []
  const input = createInterface({ input: process.stdin })
  let settled = false
  let quietTimer
  let emptyTimer
  const finish = () => {
    if (settled) return
    settled = true
    clearTimeout(quietTimer)
    clearTimeout(emptyTimer)
    input.close()
    process.stdin.pause()
    process.stdin.unref?.()
    resolve(collected)
  }
  const scheduleFinish = () => {
    clearTimeout(quietTimer)
    // dsh-library writes one complete NDJSON payload. Its macOS subprocess
    // transport may keep stdin open, so an EOF-only reader would deadlock.
    quietTimer = setTimeout(finish, 50)
  }
  input.on('line', (line) => {
    if (!line.trim()) return
    try {
      collected.push(JSON.parse(line))
      scheduleFinish()
    } catch (error) {
      settled = true
      reject(error)
    }
  })
  input.on('close', finish)
  input.on('error', reject)
  emptyTimer = setTimeout(finish, 1000)
})

const required = ['SILICONFLOW_API_KEY', 'SILICONFLOW_URL', 'EMBEDDING_MODEL']
const missing = required.filter(name => !process.env[name]?.trim())
if (missing.length)
  throw new Error(`缺少环境变量：${missing.join('、')}`)
if (rows.length === 0) process.exit(0)

const batchSize = 32
const retryableStatus = new Set([408, 409, 425, 429, 500, 502, 503, 504])
const requestEmbeddings = async (batch) => {
  let lastStatus
  for (let attempt = 0; attempt < 6; attempt += 1) {
    let response
    try {
      response = await fetch(
        `${process.env.SILICONFLOW_URL.replace(/\/$/, '')}/embeddings`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${process.env.SILICONFLOW_API_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: process.env.EMBEDDING_MODEL,
            input: batch.map(row => String(row.text)),
            encoding_format: 'float',
          }),
          signal: AbortSignal.timeout(60_000),
        },
      )
    } catch (error) {
      if (attempt === 5) throw new Error('SiliconFlow embedding 网络请求失败', { cause: error })
      await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt))
      continue
    }
    if (response.ok) return await response.json()
    lastStatus = response.status
    if (!retryableStatus.has(response.status) || attempt === 5) break
    await response.body?.cancel().catch(() => {})
    await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt))
  }
  throw new Error(`SiliconFlow embedding 请求失败（${lastStatus ?? '网络错误'}）`)
}

for (let offset = 0; offset < rows.length; offset += batchSize) {
  const batch = rows.slice(offset, offset + batchSize)
  const payload = await requestEmbeddings(batch)
  const byIndex = new Map(
    (payload.data ?? []).map(item => [item.index, item.embedding]),
  )
  for (let index = 0; index < batch.length; index += 1) {
    const vector = byIndex.get(index)
    if (!Array.isArray(vector))
      throw new Error('SiliconFlow embedding 返回不完整')
    const writable = process.stdout.write(JSON.stringify({
      index: offset + index,
      vector,
    }) + '\n')
    if (!writable) await once(process.stdout, 'drain')
  }
}
process.stdout.end()
