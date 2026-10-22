/**
 * INT-1403：IAM 用户表单邮箱格式校验 —— 邮箱非必填，但填了非法格式（如 bad-email）
 * 阻止提交并在表单内提示「邮箱格式不正确」；合法邮箱 / 留空正常提交。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const usersPort = vi.hoisted(() => ({
  getAll: vi.fn(),
  getDetail: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  assignRole: vi.fn(),
  grantPermission: vi.fn(),
  revokePermission: vi.fn(),
}))
const rolesPort = vi.hoisted(() => ({
  getAll: vi.fn(),
  getPermissions: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())

vi.mock('@/composables/system/usersPort', () => ({ usersPort }))
vi.mock('@/composables/system/rolesPort', () => ({ rolesPort }))
vi.mock('@/composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))

import UsersSection from '../UsersSection.vue'

const EMPTY_PAGE = { items: [], total: 0 }

beforeEach(() => {
  vi.clearAllMocks()
  usersPort.getAll.mockResolvedValue(EMPTY_PAGE)
  rolesPort.getAll.mockResolvedValue({ roles: [] })
  rolesPort.getPermissions.mockResolvedValue({ permissions: [] })
})

async function mountPage() {
  const w = mount(UsersSection, {
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
  return w
}

async function openCreateForm(w: any) {
  const newBtn = w.findAll('button').find((b: any) => b.text().includes('新建用户'))!
  await newBtn.trigger('click')
  await w.vm.$nextTick()
}

async function fillCreateForm(w: any, email: string) {
  await w.find('input[placeholder="登录名"]').setValue('接线测试_邮箱校验')
  await w.find('input[placeholder="user@example.com"]').setValue(email)
  await w.find('input[placeholder="至少 6 位"]').setValue('Test@123456')
}

async function clickSave(w: any) {
  const save = w.find('.user-form .btn-primary')
  await save.trigger('click')
  await flushPromises()
}

describe('UsersSection 邮箱格式校验（INT-1403）', () => {
  it('非法邮箱（bad-email）→ 不提交，表单内提示邮箱格式不正确', async () => {
    const w = await mountPage()
    await openCreateForm(w)
    await fillCreateForm(w, 'bad-email')
    await clickSave(w)

    expect(usersPort.create).not.toHaveBeenCalled()
    expect(w.text()).toContain('邮箱格式不正确')
    // 错误在表单内展示（.error-text），模态窗保持打开
    expect(w.find('.user-form .error-text').text()).toBe('邮箱格式不正确')
  })

  it('非法邮箱在编辑态同样拦截更新', async () => {
    usersPort.getAll.mockResolvedValue({
      items: [{ id: 7, username: 'existing_user', email: 'ok@example.com', status: 'active' }],
      total: 1,
    })
    const w = await mountPage()
    const editBtn = w.findAll('button').find((b: any) => b.text().includes('编辑'))!
    await editBtn.trigger('click')
    await w.vm.$nextTick()

    const emailInput = w.find('input[placeholder="user@example.com"]')
    await emailInput.setValue('not-an-email')
    await clickSave(w)

    expect(usersPort.update).not.toHaveBeenCalled()
    expect(w.text()).toContain('邮箱格式不正确')
  })

  it('合法邮箱 → 提交创建（email 原样传入）', async () => {
    usersPort.create.mockResolvedValue(undefined)
    const w = await mountPage()
    await openCreateForm(w)
    await fillCreateForm(w, 'valid@example.com')
    await clickSave(w)

    expect(usersPort.create).toHaveBeenCalledWith({
      username: '接线测试_邮箱校验',
      email: 'valid@example.com',
      password: 'Test@123456',
      role_id: undefined,
    })
    expect(w.text()).not.toContain('邮箱格式不正确')
  })

  it('邮箱留空（非必填）→ 正常提交创建', async () => {
    usersPort.create.mockResolvedValue(undefined)
    const w = await mountPage()
    await openCreateForm(w)
    await fillCreateForm(w, '')
    await clickSave(w)

    expect(usersPort.create).toHaveBeenCalledWith({
      username: '接线测试_邮箱校验',
      email: undefined,
      password: 'Test@123456',
      role_id: undefined,
    })
    expect(w.text()).not.toContain('邮箱格式不正确')
  })
})
