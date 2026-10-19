/**
 * INT-900：RolesSection 友好错误态 —— 后端 500 / 非 JSON 响应展示固定文案 + 重试按钮，
 * 不直出 client 层原始 JS 错误串；重试后后端恢复渲染真实数据。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const rolesPort = vi.hoisted(() => ({
  getAll: vi.fn(),
  getPermissions: vi.fn(),
  getDetail: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  assignPermissions: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())

vi.mock('@/composables/system/rolesPort', () => ({ rolesPort }))
vi.mock('@/composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))

import RolesSection from '../RolesSection.vue'
import { SERVER_UNAVAILABLE_COPY } from '../../errorState'

const RAW_500 = new Error("Server returned invalid JSON: 500 Internal Server Error - Failed to execute 'clone' on 'Response'")

beforeEach(() => {
  vi.clearAllMocks()
  rolesPort.getPermissions.mockResolvedValue({ permissions: [] })
})

async function mountPage() {
  const w = mount(RolesSection)
  await flushPromises()
  return w
}

describe('RolesSection 服务端 500 友好降级（INT-900）', () => {
  it('后端 500（非 JSON 响应）时展示固定文案 + 重试按钮，不直出原始 JS 错误串', async () => {
    rolesPort.getAll.mockRejectedValue(RAW_500)
    const w = await mountPage()

    expect(w.text()).toContain('加载失败')
    expect(w.text()).toContain(SERVER_UNAVAILABLE_COPY)
    expect(w.text()).toContain('重试')
    expect(w.text()).not.toContain('Server returned invalid JSON')
    expect(w.text()).not.toContain('Failed to execute')
  })

  it('重试按钮重新触发加载，后端恢复后渲染真实数据', async () => {
    rolesPort.getAll
      .mockRejectedValueOnce(RAW_500)
      .mockResolvedValueOnce({
        roles: [{ id: 1, name: '管理员', isSystem: true, description: '内置', permissions: [], userCount: 1 }],
      })
    const w = await mountPage()

    expect(w.text()).toContain(SERVER_UNAVAILABLE_COPY)

    const retry = w.findAll('button').find(b => b.text().includes('重试'))!
    await retry.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('管理员')
    expect(w.text()).not.toContain(SERVER_UNAVAILABLE_COPY)
  })

  it('业务错误（带 detail）展示后端文案而非固定文案', async () => {
    const e: any = new Error('API Request failed')
    e.detail = '无权限访问'
    rolesPort.getAll.mockRejectedValue(e)
    const w = await mountPage()

    expect(w.text()).toContain('无权限访问')
    expect(w.text()).not.toContain(SERVER_UNAVAILABLE_COPY)
  })
})
