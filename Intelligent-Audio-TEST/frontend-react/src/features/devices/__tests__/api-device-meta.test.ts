import { describe, expect, it } from 'vitest'

import { mergeApiDeviceMeta } from '@/features/devices/lib/api-device-meta'

describe('API 设备 meta 合并（INT-1621；INT-1800 起协议不再走 meta）', () => {
  it('编辑保存保留表单未识别的键（version / 旧 apiKey），只覆写 environment', () => {
    const merged = mergeApiDeviceMeta(
      { environment: 'development', version: 'v1', apiKey: '11' },
      { environment: 'production' }
    )
    expect(merged).toEqual({
      environment: 'production',
      version: 'v1',
      apiKey: '11',
    })
  })

  it('表单值为空时保留原值，不清空既有 environment', () => {
    const merged = mergeApiDeviceMeta(
      { environment: 'testing', version: 'v1' },
      { environment: '' }
    )
    expect(merged).toEqual({ environment: 'testing', version: 'v1' })
  })

  it('meta 里遗留的 protocol 键不由本函数改写（迁移脚本负责删除）', () => {
    const merged = mergeApiDeviceMeta({ protocol: 'https', version: 'v1' }, { environment: 'testing' })
    expect(merged).toEqual({ protocol: 'https', version: 'v1', environment: 'testing' })
  })

  it('新建（无原始 meta）只写 environment', () => {
    expect(mergeApiDeviceMeta(null, { environment: 'testing' })).toEqual({
      environment: 'testing',
    })
    expect(mergeApiDeviceMeta(undefined, { environment: undefined })).toEqual({})
  })

  it('不修改传入的原始 meta 对象', () => {
    const current = { version: 'v1' }
    mergeApiDeviceMeta(current, { environment: 'testing' })
    expect(current).toEqual({ version: 'v1' })
  })
})
