import { execFileSync } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/** The repository root used by the official CLI and its workspace packages. */
const rootDir = fileURLToPath(new URL('../../../..', import.meta.url))
const cliPath = join(rootDir, 'apps/cli/lib/bin.js')
const bundlePath = join(rootDir, 'packages/gerclaw/profile-bundle')
const shippedPresetRoot = join(rootDir, 'apps/cli/config/agent-presets/gerclaw')

const runDsh = (args: readonly string[], dshHome: string): string => execFileSync(
  process.execPath,
  [cliPath, ...args],
  {
    cwd: rootDir,
    env: {
      ...process.env,
      DSH_HOME: dshHome,
      GERCLAW_ROOT_DIR: rootDir,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  },
)

describe('GerClaw agent preset through the native profile Loader', () => {
  it('installs the bundle with the official plugin command and resolves gerclaw', async () => {
    const dshHome = await mkdtemp(join(tmpdir(), 'gerclaw-profile-loader-'))
    try {
      runDsh(['plugin', '--profile', 'web', 'add', `link:${bundlePath}`, '--offline'], dshHome)

      const manifest = JSON.parse(await readFile(join(dshHome, 'profiles/web/package.json'), 'utf8')) as {
        dependencies?: Record<string, string>
        dsh?: { profile?: { bundles?: string[] } }
      }
      expect(manifest.dependencies?.['@gerclaw/profile-bundle']).toBe(`link:${bundlePath}`)
      expect(manifest.dsh?.profile?.bundles).toContain('@gerclaw/profile-bundle')

      const dump = runDsh(['--profile', 'web', '--dump-config'], dshHome)
      expect(dump).toContain('default: gerclaw')
      expect(dump).toContain('id: system-prompt')
      expect(dump).toMatch(/id: system-prompt[\s\S]*?disabled: true/u)
      expect(dump).toContain('id: gerclaw-system-prompt')
      expect(dump).toContain("name: '@gerclaw/system-prompt'")
      expect(dump).toContain('id: tool-goal')
      expect(dump).toContain('id: gerclaw-prescription')

      const composition = await readFile(join(shippedPresetRoot, 'agent.cordis.yml'), 'utf8')
      expect(composition).toContain('id: planning')
      expect(composition).toContain('id: plan-mode')
      expect(composition).toContain('id: tool-goal')
    } finally {
      await rm(dshHome, { recursive: true, force: true })
    }
  })
})
