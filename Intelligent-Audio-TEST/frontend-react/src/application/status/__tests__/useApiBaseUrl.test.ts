/**
 * API 根地址解析测试（INT-512，07_文档.md §7 application/status/useApiBaseUrl.ts）：
 * 只消费 camelCase DTO；无值回退站点根 + /api；协议/凭据校验；去尾部 / 与 /v1。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { resolveApiBaseUrl } from '../useApiBaseUrl'

describe('resolveApiBaseUrl', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/user-guide')
  })

  it('字段为空时回退站点根 + /api', () => {
    const url = resolveApiBaseUrl({ apiBaseUrl: null, serverAddress: null })
    expect(url).toBe(`${window.location.origin}/api`)
  })

  it('优先 apiBaseUrl（camelCase DTO），去尾部 /v1', () => {
    const url = resolveApiBaseUrl({
      apiBaseUrl: 'https://gateway.example.com/api/v1/',
      serverAddress: 'https://fallback.example.com',
    })
    expect(url).toBe('https://gateway.example.com/api')
  })

  it('apiBaseUrl 缺失时回退 serverAddress', () => {
    const url = resolveApiBaseUrl({
      apiBaseUrl: null,
      serverAddress: 'https://host.example.com',
    })
    expect(url).toBe('https://host.example.com')
  })

  it('非 http/https 或含凭据的地址回退站点根 + /api', () => {
    expect(resolveApiBaseUrl({ apiBaseUrl: 'ftp://x/api', serverAddress: null }))
      .toBe(`${window.location.origin}/api`)
    expect(
      resolveApiBaseUrl({ apiBaseUrl: 'https://user:pw@host/api', serverAddress: null })
    ).toBe(`${window.location.origin}/api`)
  })

  it('非法 URL 回退站点根 + /api', () => {
    expect(resolveApiBaseUrl({ apiBaseUrl: 'not a url', serverAddress: null }))
      .toBe(`${window.location.origin}/api`)
  })
})
