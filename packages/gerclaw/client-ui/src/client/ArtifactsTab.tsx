import { useCallback, useEffect, useState } from 'react'
import type { TabComponentProps } from 'dsh-better-sidebar/client/service'
import { IconDownloadOutline16, IconRefreshOutline16 } from '@deepseek-ai/dsh-client-ui-primitives'

interface Artifact {
  artifactId: string
  taskId: string
  name: string
  format: string
  mediaType: string
  size: number
  createdAt: string
}

interface Bootstrap {
  artifacts?: Artifact[]
}

const artifactUrl = (artifact: Artifact): string =>
  `/gerclaw/api/artifacts/${encodeURIComponent(artifact.artifactId)}`

export interface ArtifactsTabProps extends TabComponentProps {
  subscribe?: (sessionId: string, listener: () => void) => () => void
}

export function ArtifactsTab({ visible, scope, subscribe }: ArtifactsTabProps) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [selected, setSelected] = useState<Artifact | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setError('')
    try {
      const response = await fetch(
        '/gerclaw/api/bootstrap',
        showAll
          ? {}
          : { headers: { 'x-gerclaw-session-id': scope.sessionId } },
      )
      if (!response.ok) throw new Error('产物列表暂时无法读取')
      const data = await response.json() as Bootstrap
      const next = data.artifacts ?? []
      setArtifacts(next)
      setSelected(current => current === null
        ? (next[0] ?? null)
        : (next.find(item => item.artifactId === current.artifactId) ?? next[0] ?? null))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '产物列表暂时无法读取')
    }
  }, [scope.sessionId, showAll])
  useEffect(() => {
    if (!visible) return
    void load()
    return subscribe?.(scope.sessionId, () => { void load() })
  }, [load, scope.sessionId, subscribe, visible])
  const previewUrl = selected === null ? '' : artifactUrl(selected)
  return (
    <section data-gerclaw-artifacts aria-label="产物">
      <header>
        <div><strong>产物</strong><small>{showAll ? '当前账号全部历史产物' : '当前对话生成的报告与文件'}</small></div>
        <button type="button" onClick={() => { void load() }} aria-label="刷新产物"><IconRefreshOutline16 /></button>
      </header>
      <div data-gerclaw-artifact-scope aria-label="产物范围">
        <button type="button" data-active={showAll ? 'false' : 'true'} onClick={() => { setShowAll(false) }}>当前对话</button>
        <button type="button" data-active={showAll ? 'true' : 'false'} onClick={() => { setShowAll(true) }}>全部历史</button>
      </div>
      {error && <p role="alert">{error}</p>}
      {!error && artifacts.length === 0 && <div data-gerclaw-artifact-empty>完成医疗任务后，报告会出现在这里。</div>}
      {artifacts.length > 0 && (
        <div data-gerclaw-artifact-layout>
          <ul aria-label="产物列表">
            {artifacts.map(artifact => (
              <li key={artifact.artifactId}>
                <button
                  type="button"
                  data-active={selected?.artifactId === artifact.artifactId ? 'true' : 'false'}
                  onClick={() => { setSelected(artifact) }}
                >
                  <strong>{artifact.name}</strong>
                  <small>{artifact.format.toUpperCase()} · {Math.max(1, Math.round(artifact.size / 1024))} KB</small>
                </button>
              </li>
            ))}
          </ul>
          {selected !== null && (
            <div data-gerclaw-artifact-preview>
              <div>
                <span>{selected.name}</span>
                <a href={previewUrl} download={selected.name} aria-label={`下载 ${selected.name}`}>
                  <IconDownloadOutline16 /> 下载
                </a>
              </div>
              {selected.mediaType.startsWith('image/') && <img src={previewUrl} alt={selected.name} />}
              {(selected.mediaType === 'application/pdf' || selected.mediaType === 'text/html') && (
                <iframe src={previewUrl} title={selected.name} sandbox="allow-same-origin" />
              )}
              {!selected.mediaType.startsWith('image/') && selected.mediaType !== 'application/pdf' && selected.mediaType !== 'text/html' && (
                <p>此格式可直接下载查看。</p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
