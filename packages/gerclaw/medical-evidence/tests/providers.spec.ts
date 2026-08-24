import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { MedicalEvidenceService } from '../src/index.ts'

afterEach(() => { vi.unstubAllGlobals() })

describe('medical evidence providers', () => {
  it('keeps PubMed, openFDA and MedlinePlus identities separate', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('esearch')) return Response.json({ esearchresult: { idlist: ['123'] } })
      if (url.includes('esummary')) return Response.json({ result: { 123: { title: 'Trial', sortpubdate: '2026' } } })
      if (url.includes('api.fda.gov')) return Response.json({ results: [{ id: 'label-1', openfda: { generic_name: ['aspirin'] }, warnings: ['warning'] }] })
      return new Response('<nlmSearchResult><list><document url="https://medlineplus.gov/a.html"><content name="title">Aspirin</content><content name="snippet">Health topic</content></document></list></nlmSearchResult>')
    }))
    const service = new MedicalEvidenceService(new Context())
    const rows = await service.search('aspirin')
    expect(rows.map(row => row.source)).toEqual(['PubMed', 'openFDA', 'MedlinePlus'])
    expect(rows.every(row => row.url.startsWith('https://'))).toBe(true)
  })

  it('fails the combined task when any required provider fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('esearch')) return new Response('', { status: 503 })
      if (url.includes('api.fda.gov')) return Response.json({ results: [] })
      return new Response('<nlmSearchResult/>')
    }))
    const service = new MedicalEvidenceService(new Context())
    await expect(service.search('aspirin')).rejects.toThrow('503')
  })

  it('treats an openFDA 404 as an empty drug-label result, not a source failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 404 })))
    const service = new MedicalEvidenceService(new Context())
    await expect(service.searchOpenFda('aspirin')).resolves.toEqual([])
  })
})
