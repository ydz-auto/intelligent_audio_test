import { describe, expect, it } from 'vitest'

import { mergeApiDeviceMeta } from '@/features/devices/lib/api-device-meta'

describe('API 设备 meta 合并（INT-1621）', () => {
  it('编辑保存保留表单未识别的键（version / 旧 apiKey），只覆写 protocol / environment', () => {
    const merged = mergeApiDeviceMeta(
      { protocol: 'https', environment: 'development', version: 'v1', apiKey: '11' },
      { protocol: 'http', environment: 'production' }
    )
    expect(merged).toEqual({
      protocol: 'http',
      environment: 'production',
      version: 'v1',
      apiKey: '11',
    })
  })

  it('表单值为空时保留原值，不清空既有 protocol / environment', () => {
    const merged = mergeApiDeviceMeta(
      { protocol: 'https', environment: 'testing', version: 'v1' },
      { protocol: '', environment: '' }
    )
    expect(merged).toEqual({ protocol: 'https', environment: 'testing', version: 'v1' })
  })

  it('新建（无原始 meta）只写表单两键', () => {
    expect(mergeApiDeviceMeta(null, { protocol: 'https', environment: 'testing' })).toEqual({
      protocol: 'https',
      environment: 'testing',
    })
    expect(mergeApiDeviceMeta(undefined, { protocol: 'ws', environment: undefined })).toEqual({
      protocol: 'ws',
    })
  })

  it('不修改传入的原始 meta 对象', () => {
    const current = { protocol: 'https', version: 'v1' }
    mergeApiDeviceMeta(current, { protocol: 'wss', environment: 'testing' })
    expect(current).toEqual({ protocol: 'https', version: 'v1' })
  })
})
