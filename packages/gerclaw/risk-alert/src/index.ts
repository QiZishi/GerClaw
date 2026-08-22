/** Deterministic aggregation of severe CGA, medication and conversation signals. */
import { Context, Service } from '@deepseek-ai/cordis'

export interface RiskInput {
  cga?: { followUp: string; safetyAlert?: string }
  medication?: { findings: { findingId: string; severity: string }[] }
  companion?: { urgent: boolean }
}

export interface RiskAlert {
  alertId: string
  source: 'cga' | 'medication_review' | 'chat'
  severity: 'critical' | 'high'
  title: string
  message: string
  action: string
  createdAt: string
  status: 'active' | 'acknowledged'
}

export function deriveRiskAlerts(input: RiskInput): RiskAlert[] {
  const now = new Date().toISOString()
  const alerts: RiskAlert[] = []
  const add = (
    source: RiskAlert['source'],
    severity: RiskAlert['severity'],
    key: string,
    title: string,
    message: string,
    action: string,
  ) => {
    alerts.push({
      alertId: `${source}_${key}`,
      source,
      severity,
      title,
      message,
      action,
      createdAt: now,
      status: 'active',
    })
  }
  if (input.cga?.safetyAlert) {
    add(
      'cga',
      'critical',
      'immediate',
      '需要立即安全评估',
      '本次筛查提示需要立即进行安全评估。',
      '请立即联系家人、医生或当地紧急医疗服务。',
    )
  } else if (input.cga?.followUp === 'priority') {
    add(
      'cga',
      'high',
      'followup',
      '建议尽快临床随访',
      '本次筛查提示需要尽快进行临床随访。',
      '请尽快联系医生，结合完整病史和专业评估确定下一步处理。',
    )
  }
  for (const item of input.medication?.findings ?? []) {
    if (item.severity === 'contraindicated') {
      add(
        'medication_review',
        'critical',
        item.findingId,
        '发现需要立即复核的用药风险',
        '本次用药规则核对发现禁忌级风险。',
        '请立即联系医生或药师复核原始处方和完整用药。',
      )
    } else if (item.severity === 'major') {
      add(
        'medication_review',
        'high',
        item.findingId,
        '发现需要尽快复核的用药风险',
        '本次用药规则核对发现严重级风险。',
        '请尽快联系医生或药师复核。',
      )
    }
  }
  if (input.companion?.urgent) {
    add(
      'chat',
      'critical',
      'redflag',
      '需要立即就医',
      '本次对话提示可能存在紧急健康风险。',
      '请立即联系家人、医生或当地紧急医疗服务。',
    )
  }
  return alerts
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawRiskAlert: RiskAlertService
  }
}

export class RiskAlertService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawRiskAlert')
  }

  derive(input: RiskInput): RiskAlert[] {
    return deriveRiskAlerts(input)
  }
}

export default RiskAlertService
