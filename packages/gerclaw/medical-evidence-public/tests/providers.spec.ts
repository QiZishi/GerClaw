import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { PublicMedicalEvidenceProvider } from '../src/index.ts'

afterEach(() => { vi.unstubAllGlobals() })

describe('medical evidence providers', () => {
  it('returns separate success status for all three public sources', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.includes('esearch')) return Response.json({ esearchresult: { idlist: ['123'] } })
      if (url.includes('esummary')) return Response.json({ result: { 123: { title: 'Trial', sortpubdate: '2026' } } })
      if (url.includes('api.fda.gov')) return Response.json({ results: [{ id: 'label-1', openfda: { generic_name: ['aspirin'] }, warnings: ['warning'] }] })
      return new Response('<nlmSearchResult><list><document url="https://medlineplus.gov/a.html"><content name="title">Aspirin</content><content name="snippet">Health topic</content></document></list></nlmSearchResult>')
    }))
    const service = new PublicMedicalEvidenceProvider(new Context())
    const result = await service.searchDetailed('aspirin')
    expect(result.sources.map(item => [item.source, item.status])).toEqual([
      ['PubMed', 'success'], ['openFDA', 'success'], ['MedlinePlus', 'success'],
    ])
    expect(result.results.map(row => row.source)).toEqual(['PubMed', 'openFDA', 'MedlinePlus'])
  })

  it('exposes one source failure and refuses aggregate success', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.includes('esearch')) return new Response('', { status: 503 })
      if (url.includes('api.fda.gov')) return Response.json({ results: [] })
      return new Response('<nlmSearchResult/>')
    }))
    const service = new PublicMedicalEvidenceProvider(new Context())
    await expect(service.searchDetailed('aspirin')).resolves.toMatchObject({
      sources: [
        { source: 'PubMed', status: 'failed' },
        { source: 'openFDA', status: 'success' },
        { source: 'MedlinePlus', status: 'success' },
      ],
    })
    await expect(service.search('aspirin')).rejects.toThrow('PubMed')
  })
})
