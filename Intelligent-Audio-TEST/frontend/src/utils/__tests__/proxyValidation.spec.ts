/**
 * INT-839/#4：网络代理配置校验（前后端双校验，与后端同规则）
 * 锁定口径：
 * - proxyType 非空 → proxyUrl 必填且必须带 user:pass@ 前缀；
 * - proxyType 为空 → proxyUrl 必须为空（不使用代理）；
 * - 校验基于 trim 后的地址；合法返回 null，非法返回错误文案。
 */
import { describe, it, expect } from 'vitest'
import { validateProxy } from '../proxyValidation'

describe('validateProxy（INT-839/#4 代理互斥校验）', () => {
  it('无代理（类型空 + 地址空）→ 合法', () => {
    expect(validateProxy('', '')).toBeNull()
    expect(validateProxy(null, undefined)).toBeNull()
    expect(validateProxy(undefined, '')).toBeNull()
  })

  it('proxyType 非空但 proxyUrl 为空 → 必填错误', () => {
    expect(validateProxy('http', '')).toMatch(/代理地址必填/)
    expect(validateProxy('socks5', undefined)).toMatch(/代理地址必填/)
  })

  it('proxyType 非空但 proxyUrl 缺 user:pass@ 前缀 → 格式错误', () => {
    expect(validateProxy('http', '10.0.0.1:8080')).toMatch(/user:pass@/)
    expect(validateProxy('socks5h', 'user@10.0.0.1:1080')).toMatch(/user:pass@/)
  })

  it('proxyType 为空但 proxyUrl 非空 → 互斥错误', () => {
    expect(validateProxy('', 'user:pass@10.0.0.1:8080')).toMatch(/必须为空/)
  })

  it('合法代理（user:pass@host:port）→ 合法', () => {
    expect(validateProxy('http', 'user:pass@10.0.0.1:8080')).toBeNull()
    expect(validateProxy('socks5', 'alice:pwd@proxy.example.com:1080')).toBeNull()
    expect(validateProxy('https', 'user:pass@[::1]:443')).toBeNull()
  })

  it('地址首尾空白按 trim 后校验', () => {
    expect(validateProxy('http', '  user:pass@10.0.0.1:8080  ')).toBeNull()
    expect(validateProxy('http', '   10.0.0.1:8080   ')).toMatch(/user:pass@/)
    expect(validateProxy('', '   ')).toBeNull()
  })
})
