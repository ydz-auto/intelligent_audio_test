/**
 * features/auth/lib/auth-redirect 纯函数测试（照 newAPI 纯函数粒度；
 * 对位 12_登录与错误页.md §1.1：拒绝 // 协议相对、反斜杠、非 http(s)、跨源）。
 */
import { describe, expect, it } from 'vitest'

import { sanitizeAuthRedirect } from '@/features/auth/lib/auth-redirect'

const ORIGIN = 'https://example.com'

describe('sanitizeAuthRedirect', () => {
  it('非字符串一律拒绝', () => {
    expect(sanitizeAuthRedirect(null, ORIGIN)).toBeNull()
    expect(sanitizeAuthRedirect(undefined, ORIGIN)).toBeNull()
    expect(sanitizeAuthRedirect(42, ORIGIN)).toBeNull()
    expect(sanitizeAuthRedirect({}, ORIGIN)).toBeNull()
  })

  it('空白/协议相对/反斜杠路径拒绝', () => {
    expect(sanitizeAuthRedirect('', ORIGIN)).toBeNull()
    expect(sanitizeAuthRedirect('   ', ORIGIN)).toBeNull()
    expect(sanitizeAuthRedirect('//evil.com', ORIGIN)).toBeNull()
    expect(sanitizeAuthRedirect('/\\evil', ORIGIN)).toBeNull()
  })

  it('非 http(s) 协议（javascript: 等）拒绝', () => {
    expect(
      sanitizeAuthRedirect('javascript:alert(1)', ORIGIN)
    ).toBeNull()
    expect(sanitizeAuthRedirect('file:///etc/passwd', ORIGIN)).toBeNull()
  })

  it('跨源绝对 URL 拒绝', () => {
    expect(sanitizeAuthRedirect('https://evil.com/phish', ORIGIN)).toBeNull()
  })

  it('站内路径原样放行（含 search/hash）', () => {
    expect(sanitizeAuthRedirect('/dashboard', ORIGIN)).toBe('/dashboard')
    expect(sanitizeAuthRedirect('/reports?tab=history', ORIGIN)).toBe(
      '/reports?tab=history'
    )
    expect(sanitizeAuthRedirect('/tasks#stats', ORIGIN)).toBe('/tasks#stats')
  })

  it('同源绝对 URL 折叠为 path+search+hash', () => {
    expect(
      sanitizeAuthRedirect('https://example.com/login?next=/tasks', ORIGIN)
    ).toBe('/login?next=/tasks')
  })

  it('非法 origin 拒绝', () => {
    expect(sanitizeAuthRedirect('/dashboard', 'not a url')).toBeNull()
  })
})
