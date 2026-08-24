/** Current-session-only emotional companion policy. */
import { Context, Service } from '@deepseek-ai/cordis'

export const COMPANION_SYSTEM_PROMPT = `当前对话是安全情感陪伴。以温和、尊重、自然的中文回应用户的感受。
明确自己是 AI，不是人类、亲属、医生、心理治疗师或紧急服务。不承诺排他关系或主动联系；不作诊断、治疗或用药结论。只依据当前会话文字，不调用长期记忆、检索、联网、技能或上传资料。出现紧急信号时，只强化立即求助和联系现实中的可信任人员。`

const urgentPatterns = [
  /不想活|想死|自杀|结束生命|伤害自己|杀了自己|活着没意思/,
  /胸痛|呼吸困难|喘不上气|无法呼吸|气促(?:加重)?|昏迷|意识不清|意识障碍|失去意识|叫不醒|大出血|大量出血|呕血|便血|偏瘫|口角歪斜|言语不清|言语异常|一侧.*无力|晕厥|卒中/,
]
const clauseBoundary = /[。！？!?；;，,\n]/
const negatedSignal = /(?:没有|没|无(?!论)|否认|未(?:见|出现|发生)|不伴|不存在|从未)[^。！？!?；;，,\n]{0,16}$/

export interface CompanionSignal {
  urgent: boolean
  message?: string
}

export function detectCompanionSignal(text: string): CompanionSignal {
  const urgent = text.split(clauseBoundary).some(clause =>
    urgentPatterns.some(pattern => pattern.test(clause) && !negatedSignal.test(clause)),
  )
  return urgent
    ? {
      urgent: true,
      message:
          '请立即联系身边可信任的人、医生或当地紧急医疗服务；如有紧急危险，请立即拨打当地急救电话。',
    }
    : { urgent: false }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawCompanion: CompanionService
  }
}

export class CompanionService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawCompanion')
  }

  detect(text: string): CompanionSignal {
    return detectCompanionSignal(text)
  }
}

export default CompanionService
