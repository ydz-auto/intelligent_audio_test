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
  // INT-1155：Access Token 管理区
  listAccessTokens: vi.fn(),
  createAccessToken: vi.fn(),
  updateAccessToken: vi.fn(),
  deleteAccessToken: vi.fn(),
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
  // INT-1155：Access Token 区默认空列表（各用例按需覆盖）
  ports.listAccessTokens.mockResolvedValue([])
  ports.deleteAccessToken.mockResolvedValue({})
  ports.updateAccessToken.mockResolvedValue({})
  ports.createAccessToken.mockResolvedValue({})
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

  describe('Access Token 管理区（INT-1155）', () => {
    const TOKEN_ROW = {
      id: 1,
      name: 'CI 令牌',
      tokenHint: 'a3f2',
      scopes: ['task:read'],
      expiresAt: null,
      status: 'enabled' as const,
      lastUsedAt: null,
      createdAt: '2026-10-20T02:00:00Z',
    }

    it('列表渲染：掩码末 4 位 / 永不过期 / 状态 / 操作钮', async () => {
      ports.listAccessTokens.mockResolvedValue([
        TOKEN_ROW,
        { ...TOKEN_ROW, id: 2, name: '只读令牌', tokenHint: '7c1e', scopes: [], expiresAt: '2026-12-31T23:59:59Z', status: 'disabled', lastUsedAt: '2026-10-21T05:00:00Z' },
      ])
      const w = await mountPage()
      expect(w.text()).toContain('Access Token')
      expect(w.text()).toContain('CI 令牌')
      expect(w.text()).toContain('a3f2')
      expect(w.text()).toContain('全部权限') // scopes 空 = 继承用户全部
      expect(w.text()).toContain('永不过期')
      expect(w.text()).toContain('停用')
      expect(w.text()).toContain('编辑')
      expect(w.text()).toContain('删除')
    })

    it('空态：无令牌时展示空态引导', async () => {
      const w = await mountPage()
      expect(w.text()).toContain('暂无访问令牌')
    })

    it('创建令牌钮 → 打开 ACCESS_TOKEN_CREATE 模态并刷新列表', async () => {
      const w = await mountPage()
      const callsBefore = ports.listAccessTokens.mock.calls.length
      await w.findAll('button').find((b) => b.text().includes('创建令牌'))!.trigger('click')
      expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.ACCESS_TOKEN_CREATE, expect.any(Object))
      // 无论弹窗如何关闭都刷新（创建可能已成功）
      expect(ports.listAccessTokens.mock.calls.length).toBeGreaterThan(callsBefore)
    })

    it('编辑令牌钮 → 打开 ACCESS_TOKEN_EDIT 模态（预填 token）', async () => {
      ports.listAccessTokens.mockResolvedValue([TOKEN_ROW])
      const w = await mountPage()
      // 限定在令牌表内找「编辑」钮，避免误命中个人信息卡的「编辑资料」
      await w.find('.token-table').findAll('button').find((b) => b.text().trim() === '编辑')!.trigger('click')
      expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.ACCESS_TOKEN_EDIT, expect.objectContaining({
        token: expect.objectContaining({ id: 1, name: 'CI 令牌' }),
      }))
    })

    it('启停：点击状态钮 → updateAccessToken({ status }) 并刷新', async () => {
      ports.listAccessTokens.mockResolvedValue([TOKEN_ROW])
      const w = await mountPage()
      const callsBefore = ports.listAccessTokens.mock.calls.length
      await w.findAll('button').find((b) => b.text().includes('启用'))!.trigger('click')
      await flushPromises()
      expect(ports.updateAccessToken).toHaveBeenCalledWith(1, { status: 'disabled' })
      expect(ports.listAccessTokens.mock.calls.length).toBeGreaterThan(callsBefore)
    })

    it('删除：BASIC_CONFIRM（danger）确认后下发 deleteAccessToken 并刷新', async () => {
      ports.listAccessTokens.mockResolvedValue([TOKEN_ROW])
      modalOpen.mockResolvedValue({ confirmed: true })
      const w = await mountPage()
      const callsBefore = ports.listAccessTokens.mock.calls.length
      await w.findAll('button').find((b) => b.text().includes('删除'))!.trigger('click')
      await flushPromises()
      expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.BASIC_CONFIRM, expect.objectContaining({
        title: '确认删除令牌',
        danger: true,
        confirmText: '删除',
      }))
      expect(ports.deleteAccessToken).toHaveBeenCalledWith(1)
      expect(ports.listAccessTokens.mock.calls.length).toBeGreaterThan(callsBefore)
    })

    it('删除：取消（resolve null）→ 不下发 deleteAccessToken', async () => {
      ports.listAccessTokens.mockResolvedValue([TOKEN_ROW])
      modalOpen.mockResolvedValue(null)
      const w = await mountPage()
      await w.findAll('button').find((b) => b.text().includes('删除'))!.trigger('click')
      await flushPromises()
      expect(ports.deleteAccessToken).not.toHaveBeenCalled()
    })
  })
})
