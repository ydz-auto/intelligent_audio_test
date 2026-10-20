/**
 * INT-839/#4：真实「编辑/新增 API」弹窗字段源 generateDeviceFields('api') 含代理配置
 * （修复：proxy 字段接入 CRUDFormModal 真实流程，而非孤儿 APIEditModal）
 */
import { describe, it, expect } from 'vitest'
import { generateDeviceFields } from '../deviceFields'

const fields = generateDeviceFields('api')

const byKey = (key: string) => fields.find(f => f.key === key)!

describe('generateDeviceFields("api") 代理字段（INT-839/#4）', () => {
  it('包含 proxyType 类型下拉（4 种类型，可留空 = 不使用代理）', () => {
    const proxyType = byKey('proxyType')
    expect(proxyType).toBeDefined()
    expect(proxyType.type).toBe('select')
    expect(proxyType.required).toBeFalsy()
    expect(proxyType.options).toEqual([
      { value: 'http', label: 'http' },
      { value: 'https', label: 'https' },
      { value: 'socks5', label: 'socks5' },
      { value: 'socks5h', label: 'socks5h' },
    ])
  })

  it('包含 proxyUrl 地址输入（placeholder user:pass@host:port，非必填）', () => {
    const proxyUrl = byKey('proxyUrl')
    expect(proxyUrl).toBeDefined()
    expect(proxyUrl.type).toBe('text')
    expect(proxyUrl.required).toBeFalsy()
    expect(proxyUrl.placeholder).toBe('user:pass@host:port')
  })

  it('代理字段位于 endpoints 之前（表单展示顺序合理）', () => {
    const indexOfProxyUrl = fields.findIndex(f => f.key === 'proxyUrl')
    const indexOfEndpoints = fields.findIndex(f => f.key === 'endpoints')
    expect(indexOfProxyUrl).toBeGreaterThan(-1)
    expect(indexOfEndpoints).toBeGreaterThan(indexOfProxyUrl)
  })
})
