/**
 * INT-839/#4：真实「编辑 API」弹窗（CRUDFormModal）代理配置接线 —— 组件集成测试
 *
 * 锁定口径（修复打回 P1：代理字段接入真实编辑流程，而非孤儿 APIEditModal）：
 * - generateDeviceFields('api') 生成的字段中渲染出代理类型下拉（field-proxyType）+ 代理地址输入（field-proxyUrl）；
 * - 保存前代理互斥校验与后端同规则：类型非空缺地址 / 地址缺 user:pass@ / 类型空但地址非空 → 阻止 emit('confirm')；
 * - 合法保存：emit('confirm') 载荷携带 camelCase proxyType / proxyUrl（地址 trim 后）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  playbackGetAll: vi.fn(),
  playbackScan: vi.fn(),
  devicesGetAllFlat: vi.fn(),
  devicesGetAvailableSerials: vi.fn(),
  getOptions: vi.fn(),
}))

vi.mock('../../../../composables/device/playbackPort', () => ({
  playbackPort: { getAll: mocks.playbackGetAll, scan: mocks.playbackScan },
}))
vi.mock('../../../../composables/device/devicesPort', () => ({
  devicesPort: {
    getAllFlat: mocks.devicesGetAllFlat,
    getAvailableSerials: mocks.devicesGetAvailableSerials,
    getDriverKeywords: vi.fn(async () => []),
  },
  BATCH_LIST_PARAMS: {},
}))
vi.mock('../../../../composables/device/splPort', () => ({
  splPort: { getByDevice: vi.fn(async () => ({ items: [] })), stopTestTone: vi.fn(async () => {}) },
}))
vi.mock('../../../../composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getOptions: mocks.getOptions },
}))

import CRUDFormModal from '../CRUDFormModal.vue'
import { generateDeviceFields } from '../../../../utils/deviceFields'

const apiFields = generateDeviceFields('api')

const mountModal = (formData: Record<string, any> = { id: 1, name: 'API-A' }) =>
  mount(CRUDFormModal, {
    props: {
      title: '编辑 API',
      entityName: '测试API',
      mode: 'edit',
      fields: apiFields,
      formData,
    },
  })

const submitSave = async (w: ReturnType<typeof mount>) => {
  await w.find('form').trigger('submit')
  await flushPromises()
}

const proxyTypeSelect = (w: ReturnType<typeof mount>) =>
  w.find('select#field-proxyType')
const proxyUrlInput = (w: ReturnType<typeof mount>) =>
  w.find('input#field-proxyUrl')

describe('CRUDFormModal 编辑 API 代理配置（INT-839/#4）', () => {
  beforeEach(() => {
    mocks.playbackGetAll.mockResolvedValue([])
    mocks.playbackScan.mockResolvedValue([])
    mocks.devicesGetAllFlat.mockResolvedValue([])
    mocks.devicesGetAvailableSerials.mockResolvedValue([])
    mocks.getOptions.mockResolvedValue({ algorithms: [] })
  })

  it('真实编辑弹窗渲染代理类型下拉 + 代理地址输入', async () => {
    const w = mountModal()
    await flushPromises()
    expect(proxyTypeSelect(w).exists()).toBe(true)
    expect(proxyUrlInput(w).exists()).toBe(true)
  })

  it('回显：formData 携带 proxyType / proxyUrl 时下拉与输入框选中', async () => {
    const w = mountModal({ id: 1, name: 'API-A', proxyType: 'socks5', proxyUrl: 'user:pass@10.0.0.1:1080' })
    await flushPromises()
    expect((proxyTypeSelect(w).element as HTMLSelectElement).value).toBe('socks5')
    expect((proxyUrlInput(w).element as HTMLInputElement).value).toBe('user:pass@10.0.0.1:1080')
  })

  it('proxyType 非空 → proxyUrl 必填：缺省地址阻止保存', async () => {
    const w = mountModal({ id: 1, name: 'API-A', proxyType: 'http' })
    await flushPromises()
    await proxyTypeSelect(w).setValue('http')
    await proxyUrlInput(w).setValue('')
    await submitSave(w)
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('proxyType 非空 → proxyUrl 必须带 user:pass@ 前缀', async () => {
    const w = mountModal({ id: 1, name: 'API-A', proxyType: 'http' })
    await flushPromises()
    await proxyTypeSelect(w).setValue('http')
    await proxyUrlInput(w).setValue('10.0.0.1:8080')
    await submitSave(w)
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('proxyType 为空 → proxyUrl 必须为空', async () => {
    const w = mountModal({ id: 1, name: 'API-A' })
    await flushPromises()
    await proxyUrlInput(w).setValue('user:pass@10.0.0.1:8080')
    await submitSave(w)
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('合法代理保存：confirm 载荷携带 camelCase proxyType / proxyUrl（地址 trim 后）', async () => {
    const w = mountModal({ id: 1, name: 'API-A', proxyType: 'socks5' })
    await flushPromises()
    await proxyTypeSelect(w).setValue('socks5')
    await proxyUrlInput(w).setValue('  user:pass@10.0.0.1:1080  ')
    await submitSave(w)
    const payload = w.emitted('confirm')![0][0] as { data: Record<string, any>; mode: string }
    expect(payload.mode).toBe('edit')
    expect(payload.data.proxyType).toBe('socks5')
    expect(payload.data.proxyUrl).toBe('user:pass@10.0.0.1:1080')
  })

  it('无代理（类型空 + 地址空）回归：保存照常且载荷 proxyType/proxyUrl 为 null', async () => {
    const w = mountModal({ id: 1, name: 'API-A' })
    await flushPromises()
    await submitSave(w)
    const payload = w.emitted('confirm')![0][0] as { data: Record<string, any> }
    expect(payload.data.proxyType).toBeNull()
    expect(payload.data.proxyUrl).toBeNull()
  })
})
