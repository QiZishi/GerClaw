import { describe, expect, it } from 'vitest'
import { detectCompanionSignal } from '../src/index.ts'

describe('陪伴模式紧急信号', () => {
  it.each(['我不想活了', '我想自杀', '现在胸痛并且呼吸困难', '我喘不上气', '我昏迷前想说句话', '我出现言语异常'])('识别紧急表达：%s', (text) => {
    expect(detectCompanionSignal(text)).toMatchObject({ urgent: true })
    expect(detectCompanionSignal(text).message).toContain('立即')
  })

  it.each(['今天心情不好', '我没有胸痛，只是想聊聊睡眠', '最近有点担心'])('普通表达不误报：%s', (text) => {
    expect(detectCompanionSignal(text)).toEqual({ urgent: false })
  })
})
