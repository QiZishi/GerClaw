/** GerClaw health skills plus user-facing slash-command shortcuts. */
import type { Context } from '@deepseek-ai/cordis'
import type { CommandInvocation } from '@deepseek-ai/dsh-commands'
import { createUserMessage } from '@deepseek-ai/dsh-llm'

export const name = 'gerclaw-skills'
export const inject = ['commands']

const definitions = [
  ['followup', '随访问卷', 'followup-questionnaire'],
  ['risk-assessment', '风险评估', 'risk-assessment'],
  ['health-education', '健康教育', 'health-education'],
  ['medication-reminder', '用药提醒', 'medication-reminder'],
] as const

function invokeSkill(
  invocation: CommandInvocation,
  displayName: string,
  skillName: string,
) {
  const request = invocation.rawInput.trim()
  invocation.agent.followup(createUserMessage({
    content: [{
      type: 'text',
      text: `请调用 skill 工具加载 ${skillName} 技能，并按照该技能完成以下健康任务：${request || `请先询问我完成“${displayName}”所需的信息`}`,
    }],
    source: { kind: 'user' },
  }))
  return { kind: 'success' as const, text: `已启用${displayName}，正在按该能力处理。` }
}

export function apply(ctx: Context): void {
  for (const [command, displayName, skillName] of definitions) {
    ctx.effect(
      () => ctx.commands.register({
        name: command,
        description: displayName,
        input: { hint: '描述需要处理的健康问题' },
        handler: invocation => invokeSkill(invocation, displayName, skillName),
      }),
      `gerclaw skill command: ${command}`,
    )
  }
}
