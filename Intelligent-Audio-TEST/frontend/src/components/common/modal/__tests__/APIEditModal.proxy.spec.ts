/**
 * INT-839/#4：APIEditModal 代理配置表单（类型下拉 + 地址输入 + 校验）单测
 *
 * 锁定口径（与后端同规则，前后端双校验）：
 * - proxy_type 非空 → proxy_url 必填且必须带 user:pass@ 前缀；
 * - proxy_type 为空 → proxy_url 必须为空；
 * - 合法时保存载荷携带 camelCase proxyType / proxyUrl（地址已 trim）；
 * - 无代理（proxyType 空）时行为与改动前一致（回归，不携带 proxyUrl）。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import APIEditModal from '../APIEditModal.vue'

const mountModal = (props: Record<string, unknown> = {}) =>
  mount(APIEditModal, {
    props: { title: 'API设置', ...props },
  })

const findSaveButton = (w: ReturnType<typeof mount>) =>
  w.findAll('button').find(b => b.text().includes('保存'))!

describe('APIEditModal 代理配置（INT-839/#4）', () => {
  it('代理字段随 data 回显（camelCase proxyType / proxyUrl）', async () => {
    const w = mountModal({ data: { name: 'A', proxyType: 'socks5', proxyUrl: 'user:pass@10.0.0.1:1080' } })
    expect((w.find('select').element as HTMLSelectElement).value).toBe('socks5')
    expect((w.find('input[placeholder="user:pass@host:port"]').element as HTMLInputElement).value).toBe(
      'user:pass@10.0.0.1:1080',
    )
  })

  it('proxy_type 非空 → proxy_url 必填：缺省代理地址阻止保存', async () => {
    const w = mountModal({ data: { proxyType: 'http' } })
    await findSaveButton(w).trigger('click')
    expect(w.emitted('save')).toBeUndefined()
  })

  it('proxy_type 非空 → proxy_url 必须带 user:pass@ 前缀', async () => {
    const w = mountModal({ data: { proxyType: 'http', proxyUrl: '10.0.0.1:8080' } })
    await findSaveButton(w).trigger('click')
    expect(w.emitted('save')).toBeUndefined()
  })

  it('proxy_type 为空 → proxy_url 必须为空', async () => {
    const w = mountModal({ data: { proxyUrl: 'user:pass@10.0.0.1:8080' } })
    await findSaveButton(w).trigger('click')
    expect(w.emitted('save')).toBeUndefined()
  })

  it('合法代理保存：载荷携带 camelCase proxyType / proxyUrl（地址 trim 后）', async () => {
    const w = mountModal({ data: { name: 'A', proxyType: 'socks5', proxyUrl: '  user:pass@10.0.0.1:1080  ' } })
    await findSaveButton(w).trigger('click')
    expect(w.emitted('save')![0][0]).toMatchObject({ proxyType: 'socks5', proxyUrl: 'user:pass@10.0.0.1:1080' })
  })

  it('无代理（proxyType 空）回归：保存照常且不携带 proxyUrl', async () => {
    const w = mountModal({ data: { name: 'A' } })
    await findSaveButton(w).trigger('click')
    expect(w.emitted('save')![0][0]).toMatchObject({ name: 'A' })
    expect(w.emitted('save')![0][0]).not.toHaveProperty('proxyUrl')
  })
})
