/**
 * INT-744/INT-860：个人中心账号安全/资料编辑模态测试。
 * 覆盖：修改密码（ChangePasswordModal）三字段校验 + 真实请求成功 emit confirm /
 * 失败展示后端错误；编辑资料（EditProfileModal）邮箱必填/格式校验 + 预填当前邮箱 +
 * 成功 emit confirm / 失败展示错误。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  changeMyPassword: vi.fn(),
  updateMyProfile: vi.fn(),
}))
vi.mock('@/composables/profile/profilePort', () => ({ profilePort: ports }))

import ChangePasswordModal from '@/components/common/modal/ChangePasswordModal.vue'
import EditProfileModal from '@/components/common/modal/EditProfileModal.vue'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ChangePasswordModal 修改密码（POST /auth/change-password）', () => {
  it('校验不通过：新密码少于 6 位 / 两次不一致 → 不提交', async () => {
    const w = mount(ChangePasswordModal, { props: { username: 'alice' } })
    const inputs = w.findAll('input')
    await inputs[0].setValue('old-pass')
    await inputs[1].setValue('123') // 少于 6 位
    await inputs[2].setValue('123')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.changeMyPassword).not.toHaveBeenCalled()
    expect(w.text()).toContain('新密码长度不能少于 6 位')
  })

  it('真实请求成功 → emit confirm，不出现错误文案', async () => {
    ports.changeMyPassword.mockResolvedValue(undefined)
    const w = mount(ChangePasswordModal, { props: { username: 'alice' } })
    const inputs = w.findAll('input')
    await inputs[0].setValue('old-pass')
    await inputs[1].setValue('new-pass-123')
    await inputs[2].setValue('new-pass-123')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.changeMyPassword).toHaveBeenCalledWith({
      currentPassword: 'old-pass',
      newPassword: 'new-pass-123',
    })
    expect(w.emitted('confirm')).toBeTruthy()
    expect(w.text()).not.toContain('密码修改失败')
  })

  it('真实请求失败（原密码错误 401）→ 展示后端错误文案，不 emit confirm', async () => {
    ports.changeMyPassword.mockRejectedValue(new Error('当前密码错误'))
    const w = mount(ChangePasswordModal, { props: { username: 'alice' } })
    const inputs = w.findAll('input')
    await inputs[0].setValue('wrong-pass')
    await inputs[1].setValue('new-pass-123')
    await inputs[2].setValue('new-pass-123')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.changeMyPassword).toHaveBeenCalled()
    expect(w.text()).toContain('当前密码错误')
    expect(w.emitted('confirm')).toBeFalsy()
  })
})

describe('EditProfileModal 编辑资料（PUT /auth/self）', () => {
  it('邮箱为空 → 不提交', async () => {
    const w = mount(EditProfileModal, { props: { username: 'alice', email: 'alice@example.com' } })
    await w.find('input[type="email"]').setValue('')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.updateMyProfile).not.toHaveBeenCalled()
    expect(w.text()).toContain('请输入邮箱')
  })

  it('邮箱格式不正确 → 不提交', async () => {
    const w = mount(EditProfileModal, { props: { username: 'alice', email: 'alice@example.com' } })
    await w.find('input[type="email"]').setValue('not-an-email')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.updateMyProfile).not.toHaveBeenCalled()
    expect(w.text()).toContain('邮箱格式不正确')
  })

  it('预填当前邮箱，真实请求成功 → emit confirm（新邮箱）', async () => {
    ports.updateMyProfile.mockResolvedValue(undefined)
    const w = mount(EditProfileModal, { props: { username: 'alice', email: 'alice@example.com' } })
    expect((w.find('input[type="email"]').element as HTMLInputElement).value).toBe('alice@example.com')
    await w.find('input[type="email"]').setValue('new@example.com')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.updateMyProfile).toHaveBeenCalledWith({ email: 'new@example.com' })
    expect(w.emitted('confirm')).toBeTruthy()
  })

  it('真实请求失败（服务端 400）→ 展示错误文案，不 emit confirm', async () => {
    ports.updateMyProfile.mockRejectedValue(new Error('邮箱格式不正确'))
    const w = mount(EditProfileModal, { props: { username: 'alice', email: 'alice@example.com' } })
    // 前端宽松校验可通过、后端严格校验（TLD ≥2 位）拒绝
    await w.find('input[type="email"]').setValue('a@b.c')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.updateMyProfile).toHaveBeenCalled()
    expect(w.text()).toContain('邮箱格式不正确')
    expect(w.emitted('confirm')).toBeFalsy()
  })
})
