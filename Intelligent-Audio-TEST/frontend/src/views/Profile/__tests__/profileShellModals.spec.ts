/**
 * INT-744：个人中心账号安全/资料编辑壳模态测试。
 * 覆盖：修改密码壳（ChangePasswordModal）三字段校验 + 提交提示「待后端立项」（不假成功）；
 * 编辑资料壳（EditProfileModal）邮箱校验 + 提交提示「待后端立项」。
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

describe('ChangePasswordModal 修改密码壳（F2 待 FEAT）', () => {
  it('校验不通过：新密码少于 6 位 / 两次不一致 → 不提交', async () => {
    ports.changeMyPassword.mockRejectedValue(new Error('该功能待后端接口支持（自助改密 F2 待 FEAT），暂不可用'))
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

  it('校验通过但端点未落：提交 → 提示「待后端立项」，不出现假成功', async () => {
    ports.changeMyPassword.mockRejectedValue(new Error('该功能待后端接口支持（自助改密 F2 待 FEAT），暂不可用'))
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
    expect(w.text()).toContain('待后端接口支持')
  })
})

describe('EditProfileModal 编辑资料壳（F3 待 FEAT）', () => {
  it('邮箱格式不正确 → 不提交', async () => {
    const w = mount(EditProfileModal, { props: { username: 'alice' } })
    await w.find('input[type="email"]').setValue('not-an-email')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.updateMyProfile).not.toHaveBeenCalled()
    expect(w.text()).toContain('邮箱格式不正确')
  })

  it('端点未落：提交 → 提示「待后端立项」，不出现假成功', async () => {
    ports.updateMyProfile.mockRejectedValue(new Error('该功能待后端接口支持（自我资料更新 F3 待 FEAT），暂不可用'))
    const w = mount(EditProfileModal, { props: { username: 'alice' } })
    await w.find('input[type="email"]').setValue('alice@example.com')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.updateMyProfile).toHaveBeenCalledWith({ email: 'alice@example.com' })
    expect(w.text()).toContain('待后端接口支持')
  })
})
