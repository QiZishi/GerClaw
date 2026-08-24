/** PubMed, openFDA and MedlinePlus provider adapted from dsh-medseek 0.1.1. */
import {
  MedicalEvidenceProvider,
  type MedicalEvidence,
  type MedicalEvidenceSearchResult,
  type MedicalEvidenceSource,
  type MedicalEvidenceSourceResult,
} from '@gerclaw/medical-evidence'

const bounded = (value: string, max = 1200): string => value
  .replace(/<[^>]+>/gu, ' ').replace(/\s+/gu, ' ').trim().slice(0, max)

const decodeXml = (value: string): string => value
  .replace(/&#(\d+);/gu, (_match, code: string) => String.fromCodePoint(Number(code)))
  .replace(/&#x([0-9a-f]+);/giu, (_match, code: string) => String.fromCodePoint(Number.parseInt(code, 16)))
  .replace(/&lt;/gu, '<').replace(/&gt;/gu, '>').replace(/&quot;/gu, '"')
  .replace(/&apos;/gu, "'").replace(/&amp;/gu, '&')

const aliases: ReadonlyArray<readonly [RegExp, string]> = [
  [/阿司匹林/u, 'aspirin'], [/华法林/u, 'warfarin'], [/二甲双胍/u, 'metformin'],
  [/氨氯地平/u, 'amlodipine'], [/辛伐他汀/u, 'simvastatin'], [/地高辛/u, 'digoxin'],
  [/布洛芬/u, 'ibuprofen'], [/对乙酰氨基酚/u, 'acetaminophen'],
]

const getJson = async (url: string, signal?: AbortSignal, emptyOnNotFound = false): Promise<unknown> => {
  const response = await fetch(url, {
    ...(signal === undefined ? {} : { signal }),
    headers: { Accept: 'application/json' },
  })
  if (emptyOnNotFound && response.status === 404) return {}
  if (!response.ok) throw new Error(`医学资料服务暂时不可用（${response.status}）`)
  return response.json()
}

export class PublicMedicalEvidenceProvider extends MedicalEvidenceProvider {
  async searchPubMed(query: string, signal?: AbortSignal): Promise<MedicalEvidence[]> {
    const term = query.trim().slice(0, 200)
    if (!term) return []
    const search = await getJson(
      `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=5&term=${encodeURIComponent(term)}`,
      signal,
    ) as { esearchresult?: { idlist?: string[] } }
    const ids = search.esearchresult?.idlist ?? []
    if (ids.length === 0) return []
    const summary = await getJson(
      `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=${ids.join(',')}`,
      signal,
    ) as { result?: Record<string, { title?: string; sortpubdate?: string }> }
    return ids.map(id => ({
      evidenceId: `pubmed_${id}`,
      title: bounded(summary.result?.[id]?.title ?? `PubMed ${id}`, 300),
      source: 'PubMed', locator: `PMID:${id}`,
      url: `https://pubmed.ncbi.nlm.nih.gov/${id}/`,
      snippet: summary.result?.[id]?.sortpubdate ?? '',
    }))
  }

  async searchOpenFda(query: string, signal?: AbortSignal): Promise<MedicalEvidence[]> {
    const alias = aliases.find(([pattern]) => pattern.test(query))?.[1]
    const latin = query.match(/[a-z][a-z0-9-]{2,}/giu)?.[0]
    const genericName = alias ?? latin
    if (genericName === undefined) return []
    const data = await getJson(
      `https://api.fda.gov/drug/label.json?limit=5&search=openfda.generic_name:${encodeURIComponent(`"${genericName.slice(0, 120)}"`)}`,
      signal,
      true,
    ) as { results?: Array<{
      id?: string
      openfda?: { generic_name?: string[] }
      warnings?: string[]
      drug_interactions?: string[]
    }> }
    return (data.results ?? []).map((item, index) => ({
      evidenceId: `openfda_${(item.id ?? String(index)).replace(/[^a-zA-Z0-9]/gu, '').slice(0, 32)}`,
      title: `${item.openfda?.generic_name?.[0] ?? genericName} 药品标签`,
      source: 'openFDA', locator: item.id ?? `result-${index + 1}`,
      url: 'https://open.fda.gov/apis/drug/label/',
      snippet: bounded(item.drug_interactions?.[0] ?? item.warnings?.[0] ?? ''),
    }))
  }

  async searchMedlinePlus(query: string, signal?: AbortSignal): Promise<MedicalEvidence[]> {
    const response = await fetch(
      `https://wsearch.nlm.nih.gov/ws/query?db=healthTopics&retmax=5&term=${encodeURIComponent(query.trim().slice(0, 200))}`,
      signal === undefined ? {} : { signal },
    )
    if (response.status === 404) return []
    if (!response.ok) throw new Error(`医学资料服务暂时不可用（${response.status}）`)
    const raw = await response.text()
    return [...raw.matchAll(/<document\b[^>]*\burl="([^"]+)"[^>]*>([\s\S]*?)<\/document>/giu)]
      .map((document, index) => {
        const content = document[2] ?? ''
        const field = (name: string): string => decodeXml(content.match(
          new RegExp(`<content\\s+name="${name}">([\\s\\S]*?)<\\/content>`, 'iu'),
        )?.[1] ?? '')
        const url = decodeXml(document[1] ?? '')
        return {
          evidenceId: `medlineplus_${index + 1}`,
          title: bounded(field('title') || query, 300),
          source: 'MedlinePlus' as const,
          locator: url || `result-${index + 1}`,
          url: url || 'https://medlineplus.gov/',
          snippet: bounded(field('FullSummary') || field('snippet')),
        }
      })
  }

  async searchDetailed(query: string, signal?: AbortSignal): Promise<MedicalEvidenceSearchResult> {
    const providers: Array<[
      MedicalEvidenceSource,
      () => Promise<MedicalEvidence[]>,
    ]> = [
      ['PubMed', () => this.searchPubMed(query, signal)],
      ['openFDA', () => this.searchOpenFda(query, signal)],
      ['MedlinePlus', () => this.searchMedlinePlus(query, signal)],
    ]
    const sources = await Promise.all(providers.map(async ([source, run]): Promise<MedicalEvidenceSourceResult> => {
      try {
        return { source, status: 'success', results: await run() }
      } catch (error) {
        return {
          source,
          status: 'failed',
          results: [],
          error: error instanceof Error ? error.message : '服务暂时不可用',
        }
      }
    }))
    return { sources, results: sources.flatMap(item => item.results) }
  }

  async search(query: string, signal?: AbortSignal): Promise<MedicalEvidence[]> {
    const detailed = await this.searchDetailed(query, signal)
    const failures = detailed.sources.filter(item => item.status === 'failed')
    if (failures.length > 0) {
      throw new Error(failures.map(item => `${item.source}：${item.error ?? '服务暂时不可用'}`).join('；'))
    }
    return detailed.results
  }
}

export default PublicMedicalEvidenceProvider
