/**
 * 站点配置 API 单测（接线壳 INT-607）：GET /home/site → snake_case DTO →
 * camelCase Domain；端点缺失/请求失败回落缺省配置（规范「缺省「智能语音测试平台」」）。
 * mock client 层验证转换链与失败回落。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSiteConfig } from '@/infrastructure/api/site-api'
import { DEFAULT_SITE_CONFIG } from '@/domain/models/site'

const getMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/client', () => ({
  apiClient: { get: getMock },
}))

describe('fetchSiteConfig', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('site 配置 snake→camel 转换（system_name → systemName）', async () => {
    getMock.mockResolvedValue({
      system_name: '智能语音测试平台',
      version: 'v9.7.31',
      logo: '',
      support_email: 'support@example.com',
    })
    const config = await fetchSiteConfig()
    expect(getMock).toHaveBeenCalledWith('/home/site')
    expect(config.systemName).toBe('智能语音测试平台')
    expect(config.version).toBe('v9.7.31')
    expect(config.supportEmail).toBe('support@example.com')
  })

  it('字段缺省回退默认（system_name 缺省「智能语音测试平台」）', async () => {
    getMock.mockResolvedValue({})
    const config = await fetchSiteConfig()
    expect(config.systemName).toBe(DEFAULT_SITE_CONFIG.systemName)
    expect(config.version).toBe(DEFAULT_SITE_CONFIG.version)
  })

  it('端点缺失/请求失败（404/网络异常）→ 回落缺省配置，不抛错', async () => {
    getMock.mockRejectedValue(new Error('Network Error'))
    await expect(fetchSiteConfig()).resolves.toEqual(DEFAULT_SITE_CONFIG)
  })
})
