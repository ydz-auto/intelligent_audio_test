/**
 * devicesApi.getDriverKeywords 契约测试（INT-1014）
 * 覆盖：GET /test-devices/driver-keywords 响应 → DriverKeyword Domain 转换，
 *      后端 keywords 字段为逗号分隔字符串时归一化为 string[]，避免 CRUDFormModal
 *      按数组 .join(', ') 抛 TypeError。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}))

import { request } from '../../http/client'
import { devicesApi } from '../devicesApi'

const mockedRequest = vi.mocked(request)

beforeEach(() => {
  mockedRequest.mockReset()
})

describe('getDriverKeywords', () => {
  it('请求路径为 GET /test-devices/driver-keywords', async () => {
    mockedRequest.mockResolvedValueOnce([])
    await devicesApi.getDriverKeywords()
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/test-devices/driver-keywords', null, {})
  })

  it('keywords 为逗号分隔字符串时拆分归一化为 string[]', async () => {
    mockedRequest.mockResolvedValueOnce([
      { name: 'Plaud AI 录音 v1', system: 'Android', keywords: 'android.plaud.v1' },
    ])
    const result = await devicesApi.getDriverKeywords()
    expect(result).toEqual([
      { name: 'Plaud AI 录音 v1', system: 'Android', keywords: ['android.plaud.v1'] },
    ])
  })

  it('keywords 字符串按逗号拆分并去空白/过滤空项', async () => {
    mockedRequest.mockResolvedValueOnce([
      { name: '多关键字驱动', system: 'HarmonyOS', keywords: 'plaud, ai录音,  ai record , ' },
    ])
    const result = await devicesApi.getDriverKeywords()
    expect(result[0].keywords).toEqual(['plaud', 'ai录音', 'ai record'])
  })

  it('keywords 已是数组时原样保留', async () => {
    mockedRequest.mockResolvedValueOnce([
      { name: '同传驱动', system: 'HarmonyOS', keywords: ['simultaneous', '同传'] },
    ])
    const result = await devicesApi.getDriverKeywords()
    expect(result[0].keywords).toEqual(['simultaneous', '同传'])
  })

  it('keywords 缺失/非法时兜底为空数组', async () => {
    mockedRequest.mockResolvedValueOnce([
      { name: '无关键字', system: 'All' },
      { name: '非法类型', system: 'Android', keywords: 42 },
    ])
    const result = await devicesApi.getDriverKeywords()
    expect(result[0].keywords).toEqual([])
    expect(result[1].keywords).toEqual([])
  })

  it('兼容 { data: [] } 包裹形态', async () => {
    mockedRequest.mockResolvedValueOnce({
      data: [{ name: '包裹形态', system: 'iOS', keywords: 'ios.driver' }],
    })
    const result = await devicesApi.getDriverKeywords()
    expect(result[0].keywords).toEqual(['ios.driver'])
  })
})
