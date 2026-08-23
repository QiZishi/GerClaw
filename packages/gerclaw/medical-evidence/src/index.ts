/** Official-source medical lookup providers adapted from dsh-medseek. */
import { Context, Service } from '@deepseek-ai/cordis'
export interface MedicalEvidence {
  evidenceId: string
  title: string
  source: 'PubMed' | 'openFDA' | 'MedlinePlus'
  locator: string
  url: string
  snippet: string
}
const bounded = (value: string, max = 1200) =>
  value
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max)
const decodeXml = (value: string) =>
  value
    .replace(/&#(\d+);/g, (_match, code: string) =>
      String.fromCodePoint(Number(code)),
    )
    .replace(/&#x([0-9a-f]+);/gi, (_match, code: string) =>
      String.fromCodePoint(Number.parseInt(code, 16)),
    )
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&')
const getJson = async (
  url: string,
  signal?: AbortSignal,
  emptyOnNotFound = false,
): Promise<unknown> => {
  const response = await fetch(url, {
    ...(signal === undefined ? {} : { signal }),
    headers: { Accept: 'application/json' },
  })
  if (emptyOnNotFound && response.status === 404) return {}
  if (!response.ok)
    throw new Error(`医学资料服务暂时不可用（${response.status}）`)
  return response.json()
}
export class MedicalEvidenceService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawMedicalEvidence')
  }
  async searchPubMed(
    query: string,
    signal?: AbortSignal,
  ): Promise<MedicalEvidence[]> {
    const term = query.trim().slice(0, 200)
    if (!term) return []
    const search = (await getJson(
      `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=5&term=${encodeURIComponent(term)}`,
      signal,
    )) as { esearchresult?: { idlist?: string[] } }
    const ids = search.esearchresult?.idlist ?? []
    if (ids.length === 0) return []
    const summary = (await getJson(
      `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=${ids.join(',')}`,
      signal,
    )) as { result?: Record<string, { title?: string; sortpubdate?: string }> }
    return ids.map(id => ({
      evidenceId: `pubmed_${id}`,
      title: bounded(summary.result?.[id]?.title ?? `PubMed ${id}`, 300),
      source: 'PubMed',
      locator: `PMID:${id}`,
      url: `https://pubmed.ncbi.nlm.nih.gov/${id}/`,
      snippet: summary.result?.[id]?.sortpubdate ?? '',
    }))
  }
  async searchOpenFda(
    query: string,
    signal?: AbortSignal,
  ): Promise<MedicalEvidence[]> {
    const data = (await getJson(
      `https://api.fda.gov/drug/label.json?limit=5&search=openfda.generic_name:${encodeURIComponent(`\"${query.trim().slice(0, 120)}\"`)}`,
      signal,
      true,
    )) as {
      results?: Array<{
        id?: string
        openfda?: { generic_name?: string[] }
        warnings?: string[]
        drug_interactions?: string[]
      }>
    }
    return (data.results ?? []).map((item, index) => ({
      evidenceId: `openfda_${(item.id ?? String(index)).replace(/[^a-zA-Z0-9]/g, '').slice(0, 32)}`,
      title: `${item.openfda?.generic_name?.[0] ?? query} 药品标签`,
      source: 'openFDA',
      locator: item.id ?? `result-${index + 1}`,
      url: 'https://open.fda.gov/apis/drug/label/',
      snippet: bounded(item.drug_interactions?.[0] ?? item.warnings?.[0] ?? ''),
    }))
  }
  async searchMedlinePlus(
    query: string,
    signal?: AbortSignal,
  ): Promise<MedicalEvidence[]> {
    const response = await fetch(
      `https://wsearch.nlm.nih.gov/ws/query?db=healthTopics&retmax=5&term=${encodeURIComponent(query.trim().slice(0, 200))}`,
      signal === undefined ? {} : { signal },
    )
    if (response.status === 404) return []
    if (!response.ok)
      throw new Error(`医学资料服务暂时不可用（${response.status}）`)
    const raw = await response.text()
    const docs = [...raw.matchAll(
      /<document\b[^>]*\burl="([^"]+)"[^>]*>([\s\S]*?)<\/document>/gi,
    )]
    return docs.map((doc, index) => {
      const content = doc[2] ?? ''
      const field = (name: string) =>
        decodeXml(
          content.match(
            new RegExp(`<content\\s+name="${name}">([\\s\\S]*?)<\\/content>`, 'i'),
          )?.[1] ?? '',
        )
      const url = decodeXml(doc[1] ?? '')
      const title = field('title') || query
      const snippet = field('FullSummary') || field('snippet')
      return {
        evidenceId: `medlineplus_${index + 1}`,
        title: bounded(title, 300),
        source: 'MedlinePlus',
        locator: url || `result-${index + 1}`,
        url: url || 'https://medlineplus.gov/',
        snippet: bounded(snippet),
      }
    })
  }
  async search(
    query: string,
    signal?: AbortSignal,
  ): Promise<MedicalEvidence[]> {
    const results = await Promise.all([
      this.searchPubMed(query, signal),
      this.searchOpenFda(query, signal),
      this.searchMedlinePlus(query, signal),
    ])
    return results.flat()
  }
}
declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawMedicalEvidence: MedicalEvidenceService
  }
}
export default MedicalEvidenceService
