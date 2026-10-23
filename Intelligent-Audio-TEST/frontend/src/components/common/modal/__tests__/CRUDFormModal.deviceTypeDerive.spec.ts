/**
 * INT-1434 打回修复：API 表单 deviceType 自动派生的键盘逐字输入路径。
 *
 * 锁定口径（打回 P2）：
 * - scheme 未完整（键盘逐字输入 ws:// 途中，如 w / ws: / ws:）不派生，避免中途锁错 http_api；
 * - 派生后端点再改（ws→https）自动重派生；
 * - 用户手动选择 / 表单回显值恒优先，一旦出现即停止自动派生。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

const mountModal = (formData: Record<string, any> = {}, mode: 'create' | 'edit' = 'create') =>
  mount(CRUDFormModal, {
    props: {
      title: mode === 'edit' ? '编辑 API' : '新增 API',
      entityName: '测试API',
      mode,
      fields: apiFields,
      formData,
    },
  })

const endpointInput = (w: ReturnType<typeof mount>) => w.find('input#field-endpoints-0-url')
const deviceTypeSelect = (w: ReturnType<typeof mount>) => w.find('select#field-deviceType')

/** 逐字符模拟键盘输入（中途不推进 400ms 防抖），最后一次性推进防抖窗口 */
const typeEndpoint = async (w: ReturnType<typeof mount>, chars: string) => {
  for (const prefix of Array.from(chars).map((_, i) => chars.slice(0, i + 1))) {
    await endpointInput(w).setValue(prefix)
  }
  await vi.advanceTimersByTimeAsync(400)
}

const setEndpoint = async (w: ReturnType<typeof mount>, value: string) => {
  await endpointInput(w).setValue(value)
  await vi.advanceTimersByTimeAsync(400)
}

const selectDeviceType = async (w: ReturnType<typeof mount>, value: string) => {
  await deviceTypeSelect(w).setValue(value)
}

describe('CRUDFormModal API deviceType 自动派生（INT-1434 打回修复）', () => {
  beforeEach(() => {
    mocks.playbackGetAll.mockResolvedValue([])
    mocks.playbackScan.mockResolvedValue([])
    mocks.devicesGetAllFlat.mockResolvedValue([])
    mocks.devicesGetAvailableSerials.mockResolvedValue([])
    mocks.getOptions.mockResolvedValue({ algorithms: [] })
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('键盘逐字符输入 ws://rt.example.com/stream → deviceType 派生 websocket_api（不锁错 http_api）', async () => {
    const w = mountModal()
    await flushPromises()
    await typeEndpoint(w, 'ws://rt.example.com/stream')
    expect((deviceTypeSelect(w).element as HTMLSelectElement).value).toBe('websocket_api')
  })

  it('粘贴完整 ws URL → deviceType 派生 websocket_api（原验收路径回归）', async () => {
    const w = mountModal()
    await flushPromises()
    await setEndpoint(w, 'ws://rt.example.com/stream')
    expect((deviceTypeSelect(w).element as HTMLSelectElement).value).toBe('websocket_api')
  })

  it('派生为 websocket_api 后端点改 https:// → 回派 http_api（重派生）', async () => {
    const w = mountModal()
    await flushPromises()
    await setEndpoint(w, 'ws://rt.example.com/stream')
    expect((deviceTypeSelect(w).element as HTMLSelectElement).value).toBe('websocket_api')
    await setEndpoint(w, 'https://rt.example.com/stream')
    expect((deviceTypeSelect(w).element as HTMLSelectElement).value).toBe('http_api')
  })

  it('用户手动选择后端点再改 → 显式值保持（显式优先，不再派生）', async () => {
    const w = mountModal()
    await flushPromises()
    await setEndpoint(w, 'ws://rt.example.com/stream')
    expect((deviceTypeSelect(w).element as HTMLSelectElement).value).toBe('websocket_api')
    await selectDeviceType(w, 'http_api')
    await setEndpoint(w, 'wss://rt.example.com/stream')
    expect((deviceTypeSelect(w).element as HTMLSelectElement).value).toBe('http_api')
  })

  it('表单回显 deviceType（编辑已有 API）→ 值恒优先，不被端点协议覆盖', async () => {
    const w = mountModal(
      { id: 1, name: 'API-A', deviceType: 'websocket_api', endpoints: [{ endpoint: 'https://rt.example.com/stream' }] },
      'edit'
    )
    await flushPromises()
    expect((deviceTypeSelect(w).element as HTMLSelectElement).value).toBe('websocket_api')
  })
})
