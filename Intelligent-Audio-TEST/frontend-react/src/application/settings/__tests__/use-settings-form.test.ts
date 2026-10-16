/**
 * 设置表单脏收集/差异提交测试（INT-489，INT-347 §1.3 保存链）：
 * 基线 = 服务端值；isDirty 时脏字段收集；保存只收集「脏且与基线不同」字段。
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useSettingsForm } from '../use-settings-form'

const baseline = { name: '旧名', enabled: false, days: 30 }
const optionKey = (field: keyof typeof baseline) => `site.${String(field)}`

describe('useSettingsForm', () => {
  it('初始基线不脏，collectChanges 返回 null', () => {
    const { result } = renderHook(() =>
      useSettingsForm({ baseline, optionKey })
    )
    expect(result.current.isDirty).toBe(false)
    expect(result.current.dirtyFields).toEqual([])
    expect(result.current.collectChanges()).toBeNull()
  })

  it('setField 修改后脏收集仅含与基线不同的字段', () => {
    const { result } = renderHook(() =>
      useSettingsForm({ baseline, optionKey })
    )
    act(() => result.current.setField('name', '新名'))
    expect(result.current.isDirty).toBe(true)
    expect(result.current.dirtyFields).toEqual([
      { key: 'site.name', value: '新名' },
    ])

    // 改回基线值 → 不再脏
    act(() => result.current.setField('name', '旧名'))
    expect(result.current.isDirty).toBe(false)
  })

  it('多字段脏收集按 optionKey 映射为 KV 键', () => {
    const { result } = renderHook(() =>
      useSettingsForm({ baseline, optionKey })
    )
    act(() => result.current.setField('days', 60))
    act(() => result.current.setField('enabled', true))
    expect(result.current.collectChanges()).toEqual([
      { key: 'site.enabled', value: true },
      { key: 'site.days', value: 60 },
    ])
  })

  it('reset 回基线并清空脏态', () => {
    const { result } = renderHook(() =>
      useSettingsForm({ baseline, optionKey })
    )
    act(() => result.current.setField('name', '新名'))
    act(() => result.current.reset())
    expect(result.current.draft).toEqual(baseline)
    expect(result.current.isDirty).toBe(false)
  })
})
