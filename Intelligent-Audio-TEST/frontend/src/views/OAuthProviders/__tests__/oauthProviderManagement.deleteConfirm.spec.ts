/**
 * INT-286：OAuth 提供方删除确认回归（window.confirm → BASIC_CONFIRM danger 模态）。
 *
 * 锁定口径：
 * - 删除提供方打开 BASIC_CONFIRM（title=删除提供方、danger=true），文案含提供方名与不可恢复提示
 * - 确认（open resolve）→ deleteOAuthProvider(id) 下发并刷新；取消（reject）→ 不下发
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  listOAuthProviders: vi.fn(),
  deleteOAuthProvider: vi.fn(),
  createOAuthProvider: vi.fn(),
  updateOAuthProvider: vi.fn(),
  fetchOAuthDiscovery: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())

vi.mock('@/composables/auth/authPort', () => ({ authPort: ports }))
vi.mock('@/composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))

import OAuthProviderManagement from '../OAuthProviderManagement.vue'
import { MODAL_TYPES } from '@/composables/modal/constants'

const PROVIDERS = [
  {
    id: 3, name: '华为云', slug: 'huawei', enabled: true,
    clientId: 'cid-1', authorizeUrl: 'https://idp.example.com/authorize',
    tokenUrl: 'https://idp.example.com/token', userinfoUrl: 'https://idp.example.com/userinfo',
    scopes: 'openid', userIdField: '', usernameField: '', displayNameField: '', emailField: '',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  ports.listOAuthProviders.mockResolvedValue(PROVIDERS)
  ports.deleteOAuthProvider.mockResolvedValue({})
})

async function mountPage() {
  const w = mount(OAuthProviderManagement)
  await flushPromises()
  return w
}

describe('OAuthProviderManagement 删除提供方（INT-286）', () => {
  it('打开 BASIC_CONFIRM（danger）确认模态，文案含提供方名与不可恢复提示', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountPage()

    const delBtn = w.findAll('button').find(b => b.text().includes('删除'))!
    await delBtn.trigger('click')

    expect(modalOpen).toHaveBeenCalledTimes(1)
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.BASIC_CONFIRM, expect.objectContaining({
      title: '删除提供方',
      danger: true,
      confirmText: '删除',
    }))
    const content = modalOpen.mock.calls[0][1].content as string
    expect(content).toContain('华为云')
    expect(content).toContain('不可恢复')
  })

  it('确认后按 id 下发 deleteOAuthProvider 并刷新列表', async () => {
    modalOpen.mockResolvedValue({ confirmed: true })
    const w = await mountPage()
    const callsBefore = ports.listOAuthProviders.mock.calls.length

    await w.findAll('button').find(b => b.text().includes('删除'))!.trigger('click')
    await flushPromises()

    expect(ports.deleteOAuthProvider).toHaveBeenCalledWith(3)
    expect(ports.listOAuthProviders.mock.calls.length).toBeGreaterThan(callsBefore)
  })

  it('取消（resolve null）→ 不下发删除', async () => {
    // INT-1011：取消收敛为 resolve(null)，不再是 rejection
    modalOpen.mockResolvedValue(null)
    const w = await mountPage()

    await w.findAll('button').find(b => b.text().includes('删除'))!.trigger('click')
    await flushPromises()

    expect(ports.deleteOAuthProvider).not.toHaveBeenCalled()
  })
})
