/**
 * INT-286：AccountSettings 解绑第三方账号确认回归（window.confirm → BASIC_CONFIRM danger 模态）。
 *
 * 锁定口径：
 * - 解绑打开 BASIC_CONFIRM（title=解绑第三方账号、danger=true），文案含提供方名与后果提示
 * - 确认（open resolve）→ unbindOAuthProvider(providerId) 下发；取消（reject）→ 不下发
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  listOAuthBindings: vi.fn(),
  listPublicOAuthProviders: vi.fn(),
  unbindOAuthProvider: vi.fn(),
  completeOAuthBinding: vi.fn(),
  getOAuthAuthorizeUrl: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())
const routerReplace = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: routerReplace }),
}))
vi.mock('../../../store/authStore', () => ({
  useAuthStore: () => ({ username: 'alice', roleName: '管理员' }),
}))
vi.mock('../../../composables/auth/authPort', () => ({ authPort: ports }))
vi.mock('../../../composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))

import AccountSettings from '../AccountSettings.vue'
import { MODAL_TYPES } from '../../../composables/modal/constants'

const BINDINGS = [
  { providerId: 1, providerSlug: 'github', providerName: 'GitHub', providerUserId: 'gh-1' },
]

beforeEach(() => {
  vi.clearAllMocks()
  ports.listOAuthBindings.mockResolvedValue(BINDINGS)
  ports.listPublicOAuthProviders.mockResolvedValue([])
  ports.unbindOAuthProvider.mockResolvedValue({})
})

async function mountPage() {
  const w = mount(AccountSettings)
  await flushPromises()
  return w
}

describe('AccountSettings 解绑确认（INT-286）', () => {
  it('打开 BASIC_CONFIRM（danger）确认模态，文案含提供方名与后果提示', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountPage()

    const unbindBtn = w.findAll('button').find(b => b.text().includes('解绑'))!
    await unbindBtn.trigger('click')

    expect(modalOpen).toHaveBeenCalledTimes(1)
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.BASIC_CONFIRM, expect.objectContaining({
      title: '解绑第三方账号',
      danger: true,
      confirmText: '解绑',
    }))
    const content = modalOpen.mock.calls[0][1].content as string
    expect(content).toContain('GitHub')
    expect(content).toContain('无法使用该第三方账号登录')
  })

  it('确认后按 providerId 下发 unbindOAuthProvider 并刷新列表', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountPage()
    const callsBefore = ports.listOAuthBindings.mock.calls.length

    await w.findAll('button').find(b => b.text().includes('解绑'))!.trigger('click')
    await flushPromises()

    expect(ports.unbindOAuthProvider).toHaveBeenCalledWith(1)
    expect(ports.listOAuthBindings.mock.calls.length).toBeGreaterThan(callsBefore)
  })

  it('取消（open reject）→ 不下发解绑', async () => {
    modalOpen.mockRejectedValue(new Error('cancel'))
    const w = await mountPage()

    await w.findAll('button').find(b => b.text().includes('解绑'))!.trigger('click')
    await flushPromises()

    expect(ports.unbindOAuthProvider).not.toHaveBeenCalled()
  })
})
