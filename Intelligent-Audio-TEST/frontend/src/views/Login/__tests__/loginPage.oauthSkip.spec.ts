/**
 * INT-900：登录页 OAuth 提供方请求降级 —— AUTH_MODE=off 时跳过列表请求
 * （后端该端点 500 时不发请求、不直出错误）；其余模式请求失败友好降级为隐藏按钮区。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { AuthMode } from '@/domain/enums'

const authPort = vi.hoisted(() => ({
  listPublicOAuthProviders: vi.fn(),
  getOAuthAuthorizeUrl: vi.fn(),
}))
const authStore = vi.hoisted(() => ({
  login: vi.fn(),
  loginWithToken: vi.fn(),
  logout: vi.fn(),
}))
const routerPush = vi.hoisted(() => vi.fn())

const effectiveMode = vi.hoisted(() => ({ value: 'off' as string }))

vi.mock('@/composables/auth/authPort', () => ({ authPort }))
vi.mock('@/store/authStore', () => ({ useAuthStore: () => authStore }))
vi.mock('@/domain/enums', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/domain/enums')>()
  return {
    ...actual,
    // 让页面侧 getEffectiveAuthMode 走可注入的生效模式，避免 vitest 下 import.meta.env 快照限制
    getEffectiveAuthMode: () => effectiveMode.value,
  }
})
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => ({
    query: {},
  }),
}))

import LoginPage from '../LoginPage.vue'

beforeEach(() => {
  vi.clearAllMocks()
  effectiveMode.value = 'off'
})

describe('LoginPage OAuth 提供方请求降级（INT-900）', () => {
  it('AUTH_MODE=off 时跳过 listPublicOAuthProviders 请求，不渲染第三方登录区', async () => {
    const w = mount(LoginPage)
    await flushPromises()

    expect(authPort.listPublicOAuthProviders).not.toHaveBeenCalled()
    expect(w.text()).not.toContain('第三方登录')
    expect(w.text()).not.toContain('Server returned invalid JSON')
    w.unmount()
  })

  it('非 off 模式且后端 500 时友好降级：请求发出但失败后隐藏按钮区、不直出错误', async () => {
    effectiveMode.value = 'dev'
    authPort.listPublicOAuthProviders.mockRejectedValue(
      new Error("Server returned invalid JSON: 500 Internal Server Error - Failed to execute 'clone' on 'Response'")
    )

    const w = mount(LoginPage)
    await flushPromises()

    expect(authPort.listPublicOAuthProviders).toHaveBeenCalledTimes(1)
    // 失败降级：不渲染第三方登录按钮区，也不直出原始错误串
    expect(w.text()).not.toContain('第三方登录')
    expect(w.text()).not.toContain('Server returned invalid JSON')
    w.unmount()
  })
})
