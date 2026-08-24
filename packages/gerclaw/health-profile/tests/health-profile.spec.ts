import { describe, expect, it } from 'vitest'
import { normalizeHealthProfile } from '../src/index.ts'

describe('健康档案确定性规范化', () => {
  it('创建档案、去重裁剪列表，并在更新时递增版本', () => {
    const first = normalizeHealthProfile({
      profileId: 'profile-1', displayName: '  张三  ', age: 72,
      allergies: ['青霉素', '青霉素', ''], conditions: ['高血压'],
      medications: ['药甲'], goals: ['控制血压'], preferences: ['清淡饮食'],
    })
    expect(first).toMatchObject({ profileId: 'profile-1', displayName: '张三', age: 72, revision: 1 })
    expect(first.allergies).toEqual(['青霉素'])
    const second = normalizeHealthProfile({ conditions: ['糖尿病'], weightKg: 62 }, first)
    expect(second).toMatchObject({ profileId: 'profile-1', age: 72, weightKg: 62, revision: 2 })
    expect(second.conditions).toEqual(['糖尿病'])
    expect(new Date(second.updatedAt).toString()).not.toBe('Invalid Date')
  })

  it.each([-1, 131, 72.5, Number.NaN])('拒绝非法年龄 %s', (age) => {
    expect(() => normalizeHealthProfile({ age })).toThrow('年龄必须')
  })

  it('保留明确的空数组更新语义，并限制列表长度', () => {
    const previous = normalizeHealthProfile({ profileId: 'p', allergies: ['花粉'], goals: ['目标'] })
    const next = normalizeHealthProfile({ allergies: [], goals: [] }, previous)
    expect(next.allergies).toEqual([])
    expect(next.goals).toEqual([])
    const many = normalizeHealthProfile({ conditions: Array.from({ length: 60 }, (_, index) => `病史${index}`) })
    expect(many.conditions).toHaveLength(50)
  })
})
