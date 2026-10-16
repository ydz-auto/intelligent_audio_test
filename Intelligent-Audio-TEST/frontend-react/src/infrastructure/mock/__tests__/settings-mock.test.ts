/**
 * 系统选项 mock 读取/写入测试（INT-489 返修①回归）：
 * fetchSystemOptions 必须每次返回新对象副本——保存写回后 refetch 产生新引用，
 * React Query structural sharing 判定数据变化 → 分区页基线刷新 → isDirty 清零。
 */
import { describe, expect, it } from 'vitest'

import {
  MOCK_SYSTEM_OPTIONS,
  fetchSystemOptions,
  updateSystemOption,
} from '../settings-mock'

describe('settings-mock', () => {
  it('fetchSystemOptions 每次返回新对象副本（引用变化，非同一引用）', async () => {
    const first = await fetchSystemOptions()
    const second = await fetchSystemOptions()
    expect(first).toEqual(second)
    expect(first).not.toBe(second)
    expect(first).not.toBe(MOCK_SYSTEM_OPTIONS)
  })

  it('updateSystemOption 写回后 refetch 反映新值', async () => {
    const original = MOCK_SYSTEM_OPTIONS['site.name']
    try {
      await updateSystemOption('site.name', '返修测试平台')
      const options = await fetchSystemOptions()
      expect(options['site.name']).toBe('返修测试平台')
    } finally {
      await updateSystemOption('site.name', original as string)
    }
  })
})
