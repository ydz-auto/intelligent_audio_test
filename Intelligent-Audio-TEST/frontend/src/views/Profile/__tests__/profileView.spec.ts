/**
 * INT-744：个人中心页 /profile 验收测试。
 * 覆盖：身份卡渲染 / 个人数据快捷区（收藏计数）/ OAuth 绑定解绑确认（BASIC_CONFIRM danger）/
 * 绑定回调（bind_ticket 落库）/ 区块权限门槛（我的任务/我的报告格）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  listOAuthBindings: vi.fn(),
  listPublicOAuthProviders: vi.fn(),
  unbindOAuthProvider: vi.fn(),
  completeOAuthBinding: vi.fn(),
  getOAuthAuthorizeUrl: vi.fn(),
  listFavoriteIds: vi.fn(),
  changeMyPassword: vi.fn(),
  updateMyProfile: vi.fn(),
  getMe: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())
const authLogout = vi.hoisted(() => vi.fn())
const authState = vi.hoisted(() => ({
  permissions: ['*'] as string[],
  hasPermission: (perm: string) =>
    authState.permissions.includes('*') || authState.permissions.includes(perm),
  hasAnyPermission: (...perms: string[]) =>
    authState.permissions.includes('*') || perms.some((p) => authState.permissions.includes(p)),
}))
const routeState = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
}))
const routerReplace = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeState.query }),
  useRouter: () => ({ push: vi.fn(), replace: routerReplace }),
}))
vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({
    user: { id: 1, username: 'alice', roleId: 1, roleName: '管理员', permissions: authState.permissions },
    username: 'alice',
    roleName: '管理员',
    permissions: authState.permissions,
    hasPermission: authState.hasPermission,
    hasAnyPermission: authState.hasAnyPermission,
    logout: authLogout,
  }),
}))
vi.mock('@/composables/profile/profilePort', () => ({ profilePort: ports }))
vi.mock('@/composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))
vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

import ProfileView from '../ProfileView.vue'
import { MODAL_TYPES } from '@/composables/modal/constants'

const BINDINGS = [
  { providerId: 1, providerSlug: 'github', providerName: 'GitHub', providerIcon: 'fab fa-github', providerUserId: 'gh-1' },
]
const PROVIDERS = [
  { id: 1, slug: 'github', name: 'GitHub', icon: 'fab fa-github' },
  { id: 2, slug: 'gitlab', name: 'GitLab', icon: '' },
]

beforeEach(() => {
  // resetAllMocks：清空调用记录与实现（避免 mockRejectedValue 泄漏到后续用例）
  vi.resetAllMocks()
  authState.permissions = ['*']
  routeState.query = {}
  ports.listOAuthBindings.mockResolvedValue(BINDINGS)
  ports.listPublicOAuthProviders.mockResolvedValue(PROVIDERS)
  ports.unbindOAuthProvider.mockResolvedValue({})
  ports.completeOAuthBinding.mockResolvedValue({})
  ports.listFavoriteIds.mockResolvedValue({ task: ['t1'], report: [], testcase: ['c1'] })
  ports.getMe.mockResolvedValue({
    userId: 1, username: 'alice', roleId: 1, roleName: undefined, permissions: [], email: 'alice@example.com',
  })
})

async function mountPage() {
  const w = mount(ProfileView, { global: { stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}

describe('ProfileView 个人中心（INT-744）', () => {
  it('渲染身份卡（用户名/角色/用户 ID）与个人数据快捷区（收藏计数）', async () => {
    const w = await mountPage()
    expect(w.text()).toContain('alice')
    expect(w.text()).toContain('管理员')
    expect(w.text()).toContain('用户 ID 1')
    // 收藏计数 = task 1 + report 0 + testcase 1 = 2
    expect(w.text()).toContain('我的收藏')
    expect(w.find('.stat-value').text()).toBe('2')
    // 我的任务 / 我的报告格（* 通配 → 全显）
    expect(w.text()).toContain('我的任务')
    expect(w.text()).toContain('我的报告')
  })

  it('OAuth 绑定渲染提供方网格（已绑定徽章/未绑定钮/解绑钮）', async () => {
    const w = await mountPage()
    expect(w.text()).toContain('GitHub')
    expect(w.text()).toContain('已绑定')
    expect(w.text()).toContain('gh-1')
    expect(w.text()).toContain('GitLab')
    expect(w.text()).toContain('未绑定')
  })

  it('解绑：打开 BASIC_CONFIRM（danger）确认模态，确认后下发 unbindOAuthProvider 并刷新', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountPage()
    const callsBefore = ports.listOAuthBindings.mock.calls.length

    const unbindBtn = w.findAll('button').find((b) => b.text().includes('解绑'))!
    await unbindBtn.trigger('click')
    await flushPromises()

    expect(modalOpen).toHaveBeenCalledTimes(1)
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.BASIC_CONFIRM, expect.objectContaining({
      title: '确认解绑',
      danger: true,
      confirmText: '解绑',
    }))
    const content = modalOpen.mock.calls[0][1].content as string
    expect(content).toContain('GitHub')
    expect(content).toContain('无法使用该第三方账号登录')

    expect(ports.unbindOAuthProvider).toHaveBeenCalledWith(1)
    expect(ports.listOAuthBindings.mock.calls.length).toBeGreaterThan(callsBefore)
  })

  it('解绑：取消（resolve null）→ 不下发解绑', async () => {
    // INT-1011：取消收敛为 resolve(null)，不再是 rejection
    modalOpen.mockResolvedValue(null)
    const w = await mountPage()

    await w.findAll('button').find((b) => b.text().includes('解绑'))!.trigger('click')
    await flushPromises()

    expect(ports.unbindOAuthProvider).not.toHaveBeenCalled()
  })

  it('绑定回调：bind_ticket → completeOAuthBinding 落库、清 query；bind_error → 展示错误', async () => {
    routeState.query = { bind_ticket: 'ticket-123' }
    const w = await mountPage()
    expect(ports.completeOAuthBinding).toHaveBeenCalledWith('ticket-123')
    expect(routerReplace).toHaveBeenCalledWith({ query: {} })
    await w.unmount()

    vi.clearAllMocks()
    routeState.query = { bind_error: '授权失败' }
    const w2 = await mountPage()
    expect(ports.completeOAuthBinding).not.toHaveBeenCalled()
    expect(routerReplace).toHaveBeenCalledWith({ query: {} })
  })

  it('区块权限门槛：无 task:read 隐藏「我的任务」格；无 report:read 隐藏「我的报告」格', async () => {
    authState.permissions = ['report:read']
    const w = await mountPage()
    expect(w.text()).toContain('我的收藏')
    expect(w.text()).not.toContain('我的任务')
    expect(w.text()).toContain('我的报告')
    await w.unmount()

    authState.permissions = ['task:read']
    const w2 = await mountPage()
    expect(w2.text()).toContain('我的任务')
    expect(w2.text()).not.toContain('我的报告')
  })

  it('账号安全：修改密码行 + 登录会话行保留（登录会话仍待后端立项）', async () => {
    const w = await mountPage()
    expect(w.text()).toContain('修改密码')
    expect(w.text()).toContain('登录会话')
    // 会话端点未立项，会话行仍带「待后端立项」徽标；改密行已接真实端点不带
    expect(w.text()).toContain('待后端立项')
  })

  it('邮箱：/auth/me 回传 email（INT-792）→ 个人信息卡展示', async () => {
    const w = await mountPage()
    expect(w.text()).toContain('alice@example.com')
  })

  it('编辑资料钮打开 EDIT_PROFILE 模态（预填当前邮箱）；修改密码钮打开 CHANGE_PASSWORD 模态', async () => {
    const w = await mountPage()
    await w.findAll('button').find((b) => b.text().includes('编辑资料'))!.trigger('click')
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.EDIT_PROFILE, expect.objectContaining({
      username: 'alice',
      email: 'alice@example.com',
    }))

    await w.findAll('button').find((b) => b.text().includes('修改密码'))!.trigger('click')
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.CHANGE_PASSWORD, expect.objectContaining({ username: 'alice' }))
  })

  it('修改密码成功（confirm 回调）→ 提示重新登录并清登录态跳登录页', async () => {
    modalOpen.mockResolvedValue({ currentPassword: 'x', newPassword: 'y' })
    const w = await mountPage()
    await w.findAll('button').find((b) => b.text().includes('修改密码'))!.trigger('click')
    await flushPromises()
    expect(authLogout).toHaveBeenCalled()
  })
})
