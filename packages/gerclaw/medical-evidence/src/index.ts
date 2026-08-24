/** Replaceable official-source medical evidence service definition. */
import { Context, Service } from '@deepseek-ai/cordis'

export type MedicalEvidenceSource = 'PubMed' | 'openFDA' | 'MedlinePlus'

export interface MedicalEvidence {
  evidenceId: string
  title: string
  source: MedicalEvidenceSource
  locator: string
  url: string
  snippet: string
}

export interface MedicalEvidenceSourceResult {
  source: MedicalEvidenceSource
  status: 'success' | 'failed'
  results: MedicalEvidence[]
  error?: string
}

export interface MedicalEvidenceSearchResult {
  sources: MedicalEvidenceSourceResult[]
  results: MedicalEvidence[]
}

declare module '@deepseek-ai/cordis' {
  interface Context { gerclawMedicalEvidence: MedicalEvidenceProvider }
}

export abstract class MedicalEvidenceProvider extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawMedicalEvidence') }
  abstract searchDetailed(query: string, signal?: AbortSignal): Promise<MedicalEvidenceSearchResult>
  abstract search(query: string, signal?: AbortSignal): Promise<MedicalEvidence[]>
}

export default MedicalEvidenceProvider
