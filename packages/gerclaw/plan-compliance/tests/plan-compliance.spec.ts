import { createAssistantMessage, createUserMessage, CallId } from '@deepseek-ai/dsh-llm'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import { describe, expect, it } from 'vitest'
import { needsPlanReviewContinuation } from '../src/index.ts'

const assistantPlan = (turn = 1): SessionEvent => ({
  type: 'assistant/message',
  seq: 1,
  time: 1,
  data: {
    turn,
    step: 1,
    message: createAssistantMessage({
      content: [{ type: 'text', text: '# 健康记录计划\n\n- 记录每日血压' }],
      source: { provider: 'test', model: 'test' },
    }),
  },
})

const exitPlan = (turn = 1): SessionEvent => ({
  type: 'tool/call',
  seq: 2,
  time: 2,
  data: { turn, step: 1, callId: CallId('exit-plan'), name: 'exit_plan_mode', arguments: '{}' },
})

const gerclawReminder = (turn = 1): SessionEvent => ({
  type: 'user/message',
  seq: 2,
  time: 2,
  data: {
    ...createUserMessage({
      content: [{ type: 'text', text: '计划模式一致性检查' }],
      source: { kind: 'plugin', plugin: 'gerclaw', form: 'notice', summary: '计划已生成，正在提交审核' },
    }),
    turn,
  } as never,
})

describe('GerClaw plan compliance decision', () => {
  it('continues an active Markdown plan when no exit tool or reminder exists', () => {
    expect(needsPlanReviewContinuation([assistantPlan()], 1, true)).toBe(true)
  })

  it('does not continue when the current turn already called exit_plan_mode', () => {
    expect(needsPlanReviewContinuation([assistantPlan(), exitPlan()], 1, true)).toBe(false)
  })

  it('does not duplicate an existing GerClaw reminder', () => {
    expect(needsPlanReviewContinuation([assistantPlan(), gerclawReminder()], 1, true)).toBe(false)
  })

  it('does not apply the compliance rule outside active Plan mode', () => {
    expect(needsPlanReviewContinuation([assistantPlan()], 1, false)).toBe(false)
  })
})
