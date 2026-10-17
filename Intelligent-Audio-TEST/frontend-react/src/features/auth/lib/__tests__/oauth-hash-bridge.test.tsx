/**
 * OAuth hash 桥单测（认证接线 INT-606，12_登录与错误页.md §3.5）：
 * 后端 oauth_bp.py 回调 302 固定回 `{base}/#/login?oauth_token=…` 遗留契约，
 * 组件把 hash 片段转译为 /login 的 browser-history search 参数；无 OAuth
 * 参数时零导航。
 */
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { OAuthHashCallbackBridge } from '../oauth-hash-bridge'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@/app/router', () => ({ router: { navigate: navigateMock } }))

function renderWithHash(hash: string) {
  window.location.hash = hash
  render(<OAuthHashCallbackBridge />)
  return navigateMock
}

describe('OAuthHashCallbackBridge', () => {
  it('hash #/login?oauth_token=…：转译为 /login search 参数并 replace 导航', () => {
    renderWithHash('#/login?oauth_token=t1')
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/login',
      search: { oauth_token: 't1' },
      replace: true,
    })
  })

  it('hash 携带 oauth_error：转译错误参数', () => {
    renderWithHash('#/login?oauth_error=provider_denied')
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/login',
      search: { oauth_error: 'provider_denied' },
      replace: true,
    })
  })

  it('hash 同时携带 redirect：透传', () => {
    renderWithHash('#/login?redirect=/tasks&oauth_token=t2')
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/login',
      search: { oauth_token: 't2', redirect: '/tasks' },
      replace: true,
    })
  })

  it('非 OAuth 回调 hash：不导航', () => {
    renderWithHash('#/dashboard')
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('空 hash：不导航', () => {
    renderWithHash('')
    expect(navigateMock).not.toHaveBeenCalled()
  })
})
