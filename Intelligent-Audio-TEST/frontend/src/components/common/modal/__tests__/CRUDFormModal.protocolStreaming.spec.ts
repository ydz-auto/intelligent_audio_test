/**
 * INT-2025：被测 API 表单「协议 × 流式性」两维联动 + 提交契约。
 *
 * 锁定口径：
 * - 协议切换 → 流式性按该协议缺省值联动（websocket / sse 恒流式且锁定；http / grpc 可切）；
 * - 提交载荷携带 protocol / streaming，**不再出现 device_type**；
 * - submitHandler 失败 → 不 emit('confirm')（弹窗不关闭，输入保留），成功才 confirm。
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

type Wrapper = ReturnType<typeof mount>

const mountModal = (
  formData: Record<string, any> = {},
  extraProps: Record<string, any> = {},
  mode: 'create' | 'edit' = 'create'
) =>
  mount(CRUDFormModal, {
    props: {
      title: mode === 'edit' ? '编辑 API' : '新增 API',
      entityName: '测试API',
      mode,
      fields: apiFields,
      formData,
      ...extraProps,
    },
  })

const protocolSelect = (w: Wrapper) => w.find('select#field-protocol')
const streamingRadios = (w: Wrapper) => w.findAll('input[name="field-streaming"]')
const streamingValue = (w: Wrapper) =>
  (streamingRadios(w).find(r => (r.element as HTMLInputElement).checked)?.element as HTMLInputElement | undefined)?.value

const pickProtocol = async (w: Wrapper, value: string) => {
  await protocolSelect(w).setValue(value)
  await flushPromises()
}

const fillName = async (w: Wrapper, name = '接线测试_INT2025_API') => {
  await w.find('input#field-name').setValue(name)
}

describe('INT-2025：CRUDFormModal 协议 × 流式性联动', () => {
  beforeEach(() => {
    mocks.playbackGetAll.mockResolvedValue([])
    mocks.playbackScan.mockResolvedValue([])
    mocks.devicesGetAllFlat.mockResolvedValue([])
    mocks.devicesGetAvailableSerials.mockResolvedValue([])
    mocks.getOptions.mockResolvedValue({ algorithms: [] })
  })

  it('新建缺省：协议 http + 非流式', async () => {
    const w = mountModal()
    await flushPromises()
    expect((protocolSelect(w).element as HTMLSelectElement).value).toBe('http')
    expect(streamingValue(w)).toBe('false')
  })

  it('协议切 websocket / sse → 流式性自动为流式，且选项锁定禁用', async () => {
    const w = mountModal()
    await flushPromises()
    await pickProtocol(w, 'websocket')
    expect(streamingValue(w)).toBe('true')
    expect(streamingRadios(w).every(r => (r.element as HTMLInputElement).disabled)).toBe(true)

    await pickProtocol(w, 'sse')
    expect(streamingValue(w)).toBe('true')
    expect(streamingRadios(w).every(r => (r.element as HTMLInputElement).disabled)).toBe(true)
  })

  it('协议切 grpc → 回非流式且解锁，可手动切流式', async () => {
    const w = mountModal()
    await flushPromises()
    await pickProtocol(w, 'grpc')
    expect(streamingValue(w)).toBe('false')
    expect(streamingRadios(w).every(r => (r.element as HTMLInputElement).disabled)).toBe(false)

    const streamingRadio = streamingRadios(w).find(r => (r.element as HTMLInputElement).value === 'true')!
    await streamingRadio.setValue(true)
    await flushPromises()
    expect(streamingValue(w)).toBe('true')
  })

  it('编辑回显：protocol / streaming 原样带入；越界协议回落缺省 http', async () => {
    const w = mountModal(
      { id: 1, name: 'API-A', protocol: 'websocket', streaming: true },
      {},
      'edit'
    )
    await flushPromises()
    expect((protocolSelect(w).element as HTMLSelectElement).value).toBe('websocket')
    expect(streamingValue(w)).toBe('true')

    const legacy = mountModal(
      { id: 2, name: 'API-B', protocol: 'https', streaming: false },
      {},
      'edit'
    )
    await flushPromises()
    expect((protocolSelect(legacy).element as HTMLSelectElement).value).toBe('http')
  })
})

describe('INT-2025：提交契约（protocol + streaming，不再有 device_type）', () => {
  beforeEach(() => {
    mocks.playbackGetAll.mockResolvedValue([])
    mocks.playbackScan.mockResolvedValue([])
    mocks.devicesGetAllFlat.mockResolvedValue([])
    mocks.devicesGetAvailableSerials.mockResolvedValue([])
    mocks.getOptions.mockResolvedValue({ algorithms: [] })
  })

  it('submitHandler 成功 → emit confirm，载荷带 protocol/streaming 且无 device_type', async () => {
    const submitHandler = vi.fn(async (_payload: { data: Record<string, any> }) => {})
    const w = mountModal({}, { submitHandler })
    await flushPromises()
    await fillName(w)
    await pickProtocol(w, 'websocket')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(submitHandler).toHaveBeenCalledTimes(1)
    const payload = submitHandler.mock.calls[0][0]
    expect(payload.data.protocol).toBe('websocket')
    expect(payload.data.streaming).toBe(true)
    expect('device_type' in payload.data).toBe(false)
    expect('deviceType' in payload.data).toBe(false)
    expect(w.emitted('confirm')).toBeTruthy()
  })

  it('submitHandler 抛错 → 不 emit confirm（弹窗保留输入，等用户重试）', async () => {
    const submitHandler = vi.fn(async () => {
      throw new Error('device_type 已废弃，请改用 protocol + streaming')
    })
    const w = mountModal({}, { submitHandler })
    await flushPromises()
    await fillName(w)
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(submitHandler).toHaveBeenCalledTimes(1)
    expect(w.emitted('confirm')).toBeFalsy()
    // 已填内容保留
    expect((w.find('input#field-name').element as HTMLInputElement).value).toBe('接线测试_INT2025_API')
  })
})
