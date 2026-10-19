/**
 * INT-900：系统设置页友好错误态 —— 后端 500 / 非 JSON 响应不直出 client 层原始 JS 错误串。
 *
 * 锁定口径：
 * - `isServerFailure` 能识别 client.ts 抛出的「Server returned invalid JSON: 500 ...」原始串
 * - `friendlyApiError` 对服务端/网络错误回落固定文案，对业务错误（detail）原样透传
 * - UsersSection / RolesSection / OAuthProviderManagement 在服务端失败时展示
 *   「服务暂时不可用，请稍后重试」+ 重试按钮，不渲染原始错误串
 * - 重试按钮重新触发 load()，后端恢复后渲染真实数据
 */
import { describe, it, expect } from 'vitest'
import { isServerFailure, friendlyApiError, SERVER_UNAVAILABLE_COPY } from '../../errorState'

describe('errorState 友好降级（INT-900）', () => {
  it('识别 client 层「Server returned invalid JSON」原始错误串为服务端失败', () => {
    const raw = new Error("Server returned invalid JSON: 500 Internal Server Error - Failed to execute 'clone' on 'Response'")
    expect(isServerFailure(raw)).toBe(true)
  })

  it('识别「Server returned HTML instead of JSON」与网络失败为服务端失败', () => {
    expect(isServerFailure(new Error('Server returned HTML instead of JSON: 502 Bad Gateway'))).toBe(true)
    expect(isServerFailure(new TypeError('Failed to fetch'))).toBe(true)
  })

  it('识别显式 status >= 500 为服务端失败', () => {
    const e: any = new Error('API Request failed')
    e.status = 500
    expect(isServerFailure(e)).toBe(true)
  })

  it('业务错误（带 detail）不算服务端失败', () => {
    const e: any = new Error('API Request failed')
    e.detail = '无权限访问'
    expect(isServerFailure(e)).toBe(false)
  })

  it('friendlyApiError 对服务端失败回落固定文案', () => {
    const e: any = new Error("Server returned invalid JSON: 500 Internal Server Error - Failed to execute 'clone' on 'Response'")
    expect(friendlyApiError(e, '加载失败')).toBe(SERVER_UNAVAILABLE_COPY)
  })

  it('friendlyApiError 对业务错误优先透传 detail', () => {
    const e: any = new Error('API Request failed')
    e.detail = '无权限访问'
    expect(friendlyApiError(e, '加载失败')).toBe('无权限访问')
  })
})
