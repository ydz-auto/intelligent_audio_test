/**
 * INT-839/#4：网络代理配置校验（前后端双校验，与后端同规则）
 * 锁定口径（镜像 api_test_service/infrastructure/adapters/proxy_utils.py validate_proxy）：
 * - proxyType 非空 → 必须是 http/https/socks5/socks5h 之一，proxyUrl 必填且带 user:pass@ 认证段，
 *   格式 [user:pass@]host[:port]，不含 scheme 前缀，端口若存在必须为数字；
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

  it('proxyType 不在四类型白名单 → 非法类型错误', () => {
    expect(validateProxy('socks4', 'user:pass@10.0.0.1:1080')).toMatch(/非法的代理类型/)
    expect(validateProxy('FTP', 'user:pass@10.0.0.1:21')).toMatch(/http \/ https \/ socks5 \/ socks5h/)
  })

  it('proxyUrl 含 scheme 前缀 → 拒绝（与后端同规则）', () => {
    expect(validateProxy('http', 'http://user:pass@10.0.0.1:8080')).toMatch(/scheme/)
    expect(validateProxy('socks5', 'socks5://user:pass@10.0.0.1:1080')).toMatch(/scheme/)
  })

  it('端口非数字 → 拒绝（与后端同规则）', () => {
    expect(validateProxy('http', 'user:pass@host:abc')).toMatch(/端口必须为数字/)
    expect(validateProxy('socks5h', 'user:pass@10.0.0.1:8080:extra')).toMatch(/端口必须为数字/)
  })

  it('合法代理（user:pass@host:port）→ 合法', () => {
    expect(validateProxy('http', 'user:pass@10.0.0.1:8080')).toBeNull()
    expect(validateProxy('socks5', 'alice:pwd@proxy.example.com:1080')).toBeNull()
    expect(validateProxy('https', 'user:pass@[::1]:443')).toBeNull()
    // 端口可省略（与后端 urlparse 语义一致：host 必填、端口缺省走默认）
    expect(validateProxy('http', 'user:pass@10.0.0.1')).toBeNull()
    expect(validateProxy('https', 'user:pass@[::1]')).toBeNull()
  })

  it('地址首尾空白按 trim 后校验', () => {
    expect(validateProxy('http', '  user:pass@10.0.0.1:8080  ')).toBeNull()
    expect(validateProxy('http', '   10.0.0.1:8080   ')).toMatch(/user:pass@/)
    expect(validateProxy('', '   ')).toBeNull()
  })
})
