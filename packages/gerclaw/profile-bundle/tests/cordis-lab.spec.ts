import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { boot } from '@deepseek-ai/dsh-app-boot'
import { CallId } from '@deepseek-ai/dsh-llm'
import type { SessionId } from '@deepseek-ai/dsh-session/types'

let context: Context | undefined

afterEach(async () => {
  await context?.fiber.dispose()
  context = undefined
})

const agent = {
  id: 'gerclaw-cordis-lab-session' as SessionId,
  inject() {},
  steer() {},
} as unknown as Agent

let callSequence = 0

async function execute(name: string, args: unknown) {
  if (context === undefined) throw new Error('Cordis lab is not running')
  const result = await context.tools.execute({
    agent,
    arguments: args,
    callId: CallId(`gerclaw-cordis-lab-${++callSequence}`),
    name,
    signal: new AbortController().signal,
  })
  if (result.isError) {
    const message = result.content
      .filter(block => block.type === 'text')
      .map(block => block.text)
      .join('\n')
    throw new Error(message)
  }
  return result.value
}

describe('GerClaw development-only Cordis trial profile', () => {
  it('discovers, defines, runs, inspects, stops, and undefines through registered Cordis tools', async () => {
    const config = fileURLToPath(new URL('../lab/cordis.yml', import.meta.url))
    context = await boot('gerclaw-cordis-lab', config)

    const providers = await execute('cordis_inspect_list', {}) as {
      providers: Array<{ platform: string; id: string }>
    }
    expect(providers.providers).toEqual(expect.arrayContaining([
      expect.objectContaining({ platform: 'host', id: 'Service' }),
      expect.objectContaining({ platform: 'host', id: 'Event' }),
    ]))

    const serviceContract = await execute('cordis_inspect_query', {
      platform: 'host',
      provider: 'Service',
      method: 'listService',
      input: { service: 'jobs' },
    }) as { data: unknown }
    expect(JSON.stringify(serviceContract.data)).toContain('attachController')

    const definition = await execute('cordis_define', {
      plugin: { kind: 'new', idPrefix: 'gclab' },
      name: 'GerClaw service seam trial',
      purpose: 'Verify service provision and effect cleanup before formal TypeScript implementation.',
      code: {
        host: `
          return {
            name: 'gerclaw-service-seam-trial',
            apply(ctx) {
              const state = { disposed: false };
              ctx.provide('gerclawTrialSeam', state);
              ctx.effect(() => () => { state.disposed = true; }, 'gerclaw trial cleanup');
            },
          }
        `,
      },
    }) as { pluginId: string; packageId: string }

    await execute('cordis_run', {
      pluginId: definition.pluginId,
      packageId: definition.packageId,
      mode: 'run',
    })
    expect(context.get('gerclawTrialSeam')).toMatchObject({ disposed: false })

    const inspection = await execute('cordis_inspect_self', {
      pluginId: definition.pluginId,
      packageId: definition.packageId,
    })
    expect(JSON.stringify(inspection)).toContain('gerclaw-service-seam-trial')

    const state = context.get('gerclawTrialSeam') as { disposed: boolean }
    await execute('cordis_stop', { pluginId: definition.pluginId })
    expect(state.disposed).toBe(true)
    expect(context.get('gerclawTrialSeam')).toBeUndefined()

    await execute('cordis_undefine', { pluginId: definition.pluginId })
    const inventory = await execute('cordis_inspect_self', {}) as { plugins: unknown[] }
    expect(inventory.plugins).toEqual([])
  })
})
