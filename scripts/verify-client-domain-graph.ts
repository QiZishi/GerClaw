/**
 * Enforce intra-package domain layering inside `packages/client/*\/src/client/`.
 * verify-module-graph covers package-level edges; this gate covers the
 * directory level: domain directories may import `contract/` and never each
 * other, and only the assembly point (`apply.ts` / `index.ts`) may import
 * across domains.
 *
 * Layer model (lower may not import higher):
 *   0  contract/            shared contract API (types + slot declarations)
 *   1  <domain>/ + service  domain implementations (skeleton/, chat/, ...)
 *   2  apply.ts, index.ts   assembly point and re-export shell
 *
 * Run directly:
 *   pnpm exec tsx scripts/verify-client-domain-graph.ts
 */

import { globSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, posix, resolve, sep } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const CLIENT_DIR = join(root, 'packages/client')

/** Directory names treated as the shared contract layer (importable by all). */
const CONTRACT_DIRS = new Set(['contract'])
/** Top-level client files allowed to import across domains (assembly layer). */
const ASSEMBLY_FILES = new Set(['apply.ts', 'index.ts', 'index.tsx'])

/**
 * Exact violations inherited from the imported DSH baseline. GerClaw keeps
 * those native client packages unchanged; any new file/import pair still
 * fails this gate instead of widening the exemption to a whole package.
 */
const INHERITED_DSH_BASELINE = new Set([
  'runtime/src/client/contract/session.ts\0../sessions/conversation.ts',
  'runtime/src/client/contract/sessions.ts\0../agents/scope.ts',
  'runtime/src/client/contract/sessions.ts\0../sessions/manager.ts',
  'runtime/src/client/contract/sessions.ts\0../sessions/service.ts',
  'runtime/src/client/contract/workspaces.ts\0../workspaces/service.ts',
  'runtime/src/client/sessions/service.ts\0../agents/scope.ts',
  'runtime/src/client/workspaces/manager.ts\0../sessions/notifier.ts',
  'runtime/src/client/workspaces/workspace.ts\0../sessions/notifier.ts',
  'ui-conversation/src/client/chat/ContextInjectionRow.tsx\0../reference/ReferenceIcon.tsx',
  'ui-conversation/src/client/chat/MessageItem.tsx\0../reference/ReferenceIcon.tsx',
  'ui-conversation/src/client/contract/slots.ts\0../input/blocks.ts',
  'ui-conversation/src/client/contract/slots.ts\0../input/contract.ts',
  'ui-conversation/src/client/conversation-nodes/turn-tail.ts\0../chat/turn-metrics.ts',
  'ui-conversation/src/client/input/hub.ts\0../queue/store.ts',
  'ui-conversation/src/client/queue/store.ts\0../input/contract.ts',
  'ui-conversation/src/client/service.ts\0./input/blocks.ts',
  'ui-conversation/src/client/service.ts\0./input/contract.ts',
  'ui-conversation/src/client/skeleton/ApprovalPanel.tsx\0../chat/tool-node-reader.ts',
  'ui-conversation/src/client/skeleton/ContextMeter.tsx\0../chat/StatsLine.tsx',
  'ui-conversation/src/client/skeleton/DetailsPanel.tsx\0../chat/tool-node-reader.ts',
  'ui-conversation/src/client/skeleton/InputBar.tsx\0../input/decorations.ts',
  'ui-conversation/src/client/skeleton/InputBar.tsx\0../input/contract.ts',
  'ui-conversation/src/client/skeleton/InputBar.tsx\0../reference/ReferenceIcon.tsx',
  'ui-workspace/src/client/WorkspaceBrowser.tsx\0./rows/Rows.tsx',
])

interface Violation { file: string; imported: string; reason: string }

/** Recursively list .ts/.tsx files under dir (relative paths). */
function listSources(dir: string): string[] {
  return globSync('**/*.{ts,tsx}', { cwd: dir })
    .map(rel => rel.split(sep).join('/'))
    .filter(rel => !/\.legacy\./.test(rel.slice(rel.lastIndexOf('/') + 1)))
    .sort()
}

/** First path segment of a client-relative file, or '' for top-level files. */
function domainOf(rel: string): string {
  const ix = rel.indexOf('/')
  return ix === -1 ? '' : rel.slice(0, ix)
}

/**
 * Resolve one relative import to a client-directory-relative path.
 * @param file - Importing file relative to `src/client`.
 * @param specifier - Relative module specifier from that file.
 * @returns Normalized path, preserving leading `..` segments outside `src/client`.
 */
export function resolveClientImport(file: string, specifier: string): string {
  return posix.normalize(posix.join(posix.dirname(file), specifier))
}

function checkPackage(pkgName: string, clientDir: string): Violation[] {
  const violations: Violation[] = []
  const files = listSources(clientDir)
  for (const rel of files) {
    const fromDomain = domainOf(rel)
    const isAssembly = fromDomain === '' && ASSEMBLY_FILES.has(rel)
    if (isAssembly) continue
    const source = readFileSync(join(clientDir, rel), 'utf8')
    for (const match of source.matchAll(/from\s+['"](\.[^'"]+)['"]/g)) {
      const spec = match[1]
      if (spec === undefined) continue
      const target = resolveClientImport(rel, spec)
      if (target === '..' || target.startsWith('../')) continue // package-level rules govern
      const toDomain = domainOf(target)
      if (toDomain === '' || CONTRACT_DIRS.has(toDomain)) continue // top-level shared file or contract layer
      if (fromDomain === toDomain) continue // inside one domain
      violations.push({
        file: `${pkgName}/src/client/${rel}`,
        imported: spec,
        reason: fromDomain === ''
          ? `top-level non-assembly file imports domain "${toDomain}" (only apply/index may assemble)`
          : `domain "${fromDomain}" imports sibling domain "${toDomain}" (route shared API through contract/)`,
      })
    }
  }
  return violations
}

function main(): void {
  const discovered: Violation[] = []
  for (const pkg of readdirSync(CLIENT_DIR)) {
    const clientDir = join(CLIENT_DIR, pkg, 'src/client')
    try {
      if (!statSync(clientDir).isDirectory()) continue
    } catch {
      // No client half in this package — nothing to layer-check.
      continue
    }
    discovered.push(...checkPackage(pkg, clientDir))
  }
  const violations = discovered.filter(v =>
    !INHERITED_DSH_BASELINE.has(`${v.file}\0${v.imported}`),
  )

  if (violations.length > 0) {
    console.error(`verify-client-domain-graph: ${violations.length} violation(s):`)
    for (const v of violations) console.error(`  ${v.file} -> ${v.imported}\n    ${v.reason}`)
    process.exitCode = 1
    return
  }
  const inherited = discovered.length - violations.length
  console.log(
    `verify-client-domain-graph: client domain layering clean (${inherited} exact inherited DSH baseline edge(s) unchanged).`,
  )
}

if (import.meta.filename === resolve(process.argv[1] ?? '')) main()
