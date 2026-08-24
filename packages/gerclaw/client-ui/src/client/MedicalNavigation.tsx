import { useCallback, useRef, useState } from 'react'
import { Tooltip } from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import {
  AssessmentIcon, ChatIcon, MedicationIcon, MoreIcon, PrescriptionIcon, ProfileIcon,
} from './icons.tsx'
import { Modal } from './Modal.tsx'
import { MedicalFeature, type MedicalRemoteActions } from './MedicalFeature.tsx'

export type FeatureId = 'cga' | 'medication' | 'profile' | 'chronic' | 'risks' | 'companion' | 'documents' | 'more'

const entries = [
  { id: 'chat', label: '健康对话', icon: ChatIcon },
  { id: 'prescription', label: '五大处方', icon: PrescriptionIcon },
  { id: 'cga', label: '综合量表', icon: AssessmentIcon },
  { id: 'medication', label: '用药核对', icon: MedicationIcon },
  { id: 'profile', label: '健康档案', icon: ProfileIcon },
  { id: 'more', label: '更多', icon: MoreIcon },
] as const

const featureTitles: Record<FeatureId, string> = {
  cga: '综合量表',
  medication: '用药核对',
  profile: '健康档案',
  more: '更多健康服务',
  chronic: '慢病记录',
  risks: '风险提醒',
  companion: '暖心陪伴',
  documents: '文档与医学资料',
}

export interface MedicalNavigationInjected {
  getSessionId: () => string | undefined
  ensureSessionId: () => Promise<string>
  startPrescription: (sessionId: string) => Promise<void>
  medicalRemote: MedicalRemoteActions
}
type MedicalNavigationProps = PropsRuntime<'sidebar.footer.action'> & InjectFace<MedicalNavigationInjected>

export function MedicalNavigation({ wide, getSessionId, ensureSessionId, startPrescription, medicalRemote }: MedicalNavigationProps) {
  const [feature, setFeature] = useState<FeatureId | null>(null)
  const [sessionId, setSessionId] = useState<string | undefined>(() => getSessionId())
  const [opening, setOpening] = useState<FeatureId | 'prescription' | null>(null)
  const [error, setError] = useState('')
  const requestRef = useRef(0)
  const close = useCallback(() => { setFeature(null) }, [])
  const openFeature = useCallback((target: FeatureId): void => {
    const request = ++requestRef.current
    setOpening(target)
    setError('')
    void ensureSessionId().then((id) => {
      if (request !== requestRef.current) return
      setSessionId(id)
      setFeature(target)
    }).catch((reason: unknown) => {
      if (request !== requestRef.current) return
      setError(reason instanceof Error ? reason.message : '暂时无法开始健康任务，请稍后重试')
    }).finally(() => {
      if (request === requestRef.current) setOpening(null)
    })
  }, [ensureSessionId])
  const openPrescription = useCallback((): void => {
    const request = ++requestRef.current
    setOpening('prescription')
    setError('')
    setFeature(null)
    void ensureSessionId().then(async (id) => {
      if (request !== requestRef.current) return
      setSessionId(id)
      await startPrescription(id)
      window.setTimeout(() => {
        document.querySelector<HTMLTextAreaElement>('[data-composer-card] textarea')?.focus()
      }, 0)
    }).catch((reason: unknown) => {
      if (request !== requestRef.current) return
      setError(reason instanceof Error ? reason.message : '暂时无法开始五大处方，请稍后重试')
    }).finally(() => {
      if (request === requestRef.current) setOpening(null)
    })
  }, [ensureSessionId, startPrescription])
  return (
    <>
      <nav data-gerclaw-medical-nav data-wide={String(wide)} aria-label="健康功能">
        {entries.map(({ id, label, icon: EntryIcon }) => (
          <Tooltip key={id} label={label} side="right" delayMs={350}>
            <button
              type="button"
              aria-label={label}
              aria-busy={opening === id}
              disabled={opening !== null}
              onClick={() => {
                if (id === 'chat') {
                  setFeature(null)
                  document.querySelector<HTMLElement>('textarea')?.focus()
                } else if (id === 'prescription') openPrescription()
                else openFeature(id)
              }}
            >
              <EntryIcon size={19} />
              {wide && <span>{label}</span>}
            </button>
          </Tooltip>
        ))}
      </nav>
      {error && <div data-gerclaw-navigation-error role="alert">{error}</div>}
      {feature !== null && (
        <Modal title={featureTitles[feature]} onClose={close}>
          {feature === 'more' ? (
            <div data-gerclaw-feature-grid>
              {([
                ['chronic', '慢病记录', '记录血压、血糖等指标并查看趋势'],
                ['risks', '风险提醒', '汇总量表、用药和对话中的重要信号'],
                ['companion', '暖心陪伴', '进行支持性对话并识别紧急求助信号'],
                ['documents', '文档库', '检索本账号资料和 GerClaw 本地知识库'],
              ] as const).map(([target, title, description]) => (
                <button key={title} type="button" onClick={() => { openFeature(target) }}>
                  <strong>{title}</strong><br />
                  <small>{description}</small>
                </button>
              ))}
            </div>
          ) : (
            sessionId && <MedicalFeature feature={feature} sessionId={sessionId} remote={medicalRemote} />
          )}
        </Modal>
      )}
    </>
  )
}
