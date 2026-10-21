/**
 * INT-1155：个人中心 Access Token 创建/编辑模态测试。
 * 覆盖：创建（表单校验 + 提交走 profilePort.createAccessToken → 二段态明文仅一次展示 +
 * 复制钮 + 「我已保存，关闭」才 emit confirm / 失败展示错误）；编辑（预填 + 启停 toggle +
 * 保存成功 emit confirm / 失败展示错误）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const ports = vi.hoisted(() => ({
  createAccessToken: vi.fn(),
  updateAccessToken: vi.fn(),
}))
vi.mock('@/composables/profile/profilePort', () => ({ profilePort: ports }))

import AccessTokenCreateModal from '@/components/common/modal/AccessTokenCreateModal.vue'
import AccessTokenEditModal from '@/components/common/modal/AccessTokenEditModal.vue'
import type { AccessToken } from '@/domain/model/accessToken'

const TOKEN: AccessToken = {
  id: 1,
  name: 'CI 令牌',
  tokenHint: 'a3f2',
  scopes: ['task:read'],
  expiresAt: '2026-12-31T23:59:59Z',
  status: 'enabled',
  lastUsedAt: null,
  createdAt: '2026-10-20T02:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AccessTokenCreateModal 创建（POST /auth/access-tokens）', () => {
  it('名称为空 → 不提交并提示', async () => {
    const w = mount(AccessTokenCreateModal)
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.createAccessToken).not.toHaveBeenCalled()
    expect(w.text()).toContain('请输入令牌名称')
  })

  it('自定义有效期未填 → 不提交并提示', async () => {
    const w = mount(AccessTokenCreateModal)
    await w.find('#at-name').setValue('演示令牌')
    await w.find('#at-expires').setValue('custom')
    await flushPromises()
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.createAccessToken).not.toHaveBeenCalled()
    expect(w.text()).toContain('请选择自定义过期时间')
  })

  it('提交成功 → 二段态明文仅一次展示 + 复制钮，且未 emit confirm', async () => {
    const created = {
      accessToken: `at_${'a'.repeat(32)}`,
      token: { ...TOKEN, id: 2, name: 'CI 测试', tokenHint: 'aaaa' },
    }
    ports.createAccessToken.mockResolvedValue(created)
    const w = mount(AccessTokenCreateModal)
    await w.find('#at-name').setValue('CI 测试')
    await w.find('.scope-option input[type="checkbox"]').setValue(true) // 勾选首个权限点
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.createAccessToken).toHaveBeenCalledWith(expect.objectContaining({
      name: 'CI 测试',
      scopes: ['task:read'],
    }))
    // 二段态：明文 + 仅此一次提示
    expect(w.find('[data-testid="token-plaintext"]').text()).toBe(created.accessToken)
    expect(w.text()).toContain('仅此一次显示')
    const copyBtns = w.findAll('button').filter((b) => b.text().includes('复制'))
    expect(copyBtns.length).toBeGreaterThan(0)
    // 未 emit confirm（弹窗需保留供用户复制）
    expect(w.emitted('confirm')).toBeFalsy()
  })

  it('「我已保存，关闭」→ emit confirm（携带创建结果）', async () => {
    const created = {
      accessToken: `at_${'b'.repeat(32)}`,
      token: { ...TOKEN, id: 2, name: 'CI 测试', tokenHint: 'bbbb' },
    }
    ports.createAccessToken.mockResolvedValue(created)
    const w = mount(AccessTokenCreateModal)
    await w.find('#at-name').setValue('CI 测试')
    await w.find('form').trigger('submit')
    await flushPromises()
    const doneBtn = w.findAll('button').find((b) => b.text().includes('我已保存，关闭'))!
    await doneBtn.trigger('click')
    expect(w.emitted('confirm')).toBeTruthy()
    expect((w.emitted('confirm')![0] as any[])[0]).toEqual(created)
  })

  it('创建失败（后端错误文案）→ 展示错误，不进二段态', async () => {
    ports.createAccessToken.mockRejectedValue(new Error('令牌名称已存在'))
    const w = mount(AccessTokenCreateModal)
    await w.find('#at-name').setValue('重复名')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('令牌名称已存在')
    expect(w.find('[data-testid="token-plaintext"]').exists()).toBe(false)
    expect(w.emitted('confirm')).toBeFalsy()
  })
})

describe('AccessTokenEditModal 编辑（PATCH /auth/access-tokens/{id}）', () => {
  it('预填当前名称 / scopes / 有效期 / 状态', async () => {
    const w = mount(AccessTokenEditModal, { props: { token: TOKEN } })
    expect((w.find('#at-edit-name').element as HTMLInputElement).value).toBe('CI 令牌')
    // task:read 已勾选
    expect(w.find('.scope-option.checked').text()).toContain('task:read')
    expect(w.find('#at-edit-expires').element as HTMLSelectElement).toHaveProperty('value', 'custom')
    expect(w.find('.status-switch').text()).toContain('启用')
  })

  it('启停 toggle + 保存成功 → updateAccessToken 下发 status 并 emit confirm', async () => {
    ports.updateAccessToken.mockResolvedValue({ ...TOKEN, status: 'disabled', name: '已改名' })
    const w = mount(AccessTokenEditModal, { props: { token: TOKEN } })
    await w.find('.status-switch').trigger('click')
    await w.find('#at-edit-name').setValue('已改名')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(ports.updateAccessToken).toHaveBeenCalledWith(1, expect.objectContaining({
      name: '已改名',
      status: 'disabled',
      scopes: ['task:read'],
    }))
    expect(w.emitted('confirm')).toBeTruthy()
  })

  it('保存失败（后端错误文案）→ 展示错误，不 emit confirm', async () => {
    ports.updateAccessToken.mockRejectedValue(new Error('无权限修改该令牌'))
    const w = mount(AccessTokenEditModal, { props: { token: TOKEN } })
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('无权限修改该令牌')
    expect(w.emitted('confirm')).toBeFalsy()
  })

  it('取消 → emit cancel', async () => {
    const w = mount(AccessTokenEditModal, { props: { token: TOKEN } })
    await w.findAll('button').find((b) => b.text().includes('取消'))!.trigger('click')
    expect(w.emitted('cancel')).toBeTruthy()
  })
})
