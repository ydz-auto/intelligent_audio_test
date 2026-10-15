/**
 * INT-289：SPLMapping 列表页加载/错误态——搜索失败可见错误提示、加载态暴露、统计/设备加载失败提示。
 *
 * 旧实现：searchMappings / fetchStats / fetchDevices 失败仅 console.error，
 *   无 loading 指示，页面把「接口坏了」误呈现为「无数据」。
 *
 * 锁定契约：
 * 1. searchMappings 暴露 loading 并在请求期间置位、结束后复位；
 * 2. searchMappings 失败走 useNotification.error，且不清空既有映射；
 * 3. fetchStats 失败走 useNotification.error；
 * 4. fetchDevices 失败走 useNotification.error。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const splPort = vi.hoisted(() => ({
  getAll: vi.fn(),
  getStats: vi.fn(),
}))
const playbackPort = vi.hoisted(() => ({
  getAll: vi.fn(),
}))
const notifications = vi.hoisted(() => ({ error: vi.fn(), show: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() }))

vi.mock('@/composables/device/splPort', () => ({ splPort }))
vi.mock('@/composables/device/playbackPort', () => ({ playbackPort }))
vi.mock('@/composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('@/composables/modal/useModal', () => ({
  getModalManager: () => ({ open: vi.fn(), close: vi.fn(), closeAll: vi.fn(), getActiveModals: () => [], updateModalProps: vi.fn(), registerModal: vi.fn() }),
  provideModal: vi.fn(),
}))
vi.mock('@/composables/modal/constants', () => ({
  MODAL_TYPES: { CRUD_FORM: 'CRUD_FORM', DETAIL_VIEW: 'DETAIL_VIEW', DELETE_CONFIRM: 'DELETE_CONFIRM', IMPORT_EXPORT: 'IMPORT_EXPORT' },
}))
vi.mock('chart.js/auto', () => ({
  default: class ChartMock {
    destroy() {}
  },
}))

import { useSplMapping } from '../useSplMapping'

beforeEach(() => {
  vi.clearAllMocks()
  splPort.getAll.mockResolvedValue({ items: [] })
  splPort.getStats.mockResolvedValue({ total: 0, calibrated: 0, uncalibrated: 0, associatedDevices: 0 })
  playbackPort.getAll.mockResolvedValue([])
})

describe('useSplMapping 加载/错误态（INT-289）', () => {
  it('searchMappings 请求期间 loading 置位、结束后复位（成功路径）', async () => {
    let resolveFetch!: (v: any) => void
    splPort.getAll.mockReturnValue(new Promise(r => { resolveFetch = r }))
    const view = useSplMapping()

    const promise = view.searchMappings()
    expect(view.loading.value).toBe(true)

    resolveFetch({ items: [{ id: 1, name: 'm1' }] })
    await promise

    expect(view.loading.value).toBe(false)
    expect(view.mappingData.value.length).toBe(1)
  })

  it('searchMappings 失败：notification.error 提示，loading 复位，既有映射保留', async () => {
    splPort.getAll.mockRejectedValue(new Error('服务不可用'))
    const view = useSplMapping()
    view.mappingData.value = [{ id: 1, name: '旧映射' }] as any

    await view.searchMappings()

    expect(notifications.error).toHaveBeenCalledTimes(1)
    expect(notifications.error).toHaveBeenCalledWith('获取映射列表失败: 服务不可用')
    expect(view.loading.value).toBe(false)
    expect(view.mappingData.value.length).toBe(1)
  })

  it('fetchStats 失败：notification.error 提示', async () => {
    splPort.getStats.mockRejectedValue(new Error('统计接口 500'))
    const view = useSplMapping()

    await view.fetchStats()

    expect(notifications.error).toHaveBeenCalledWith('获取统计数据失败: 统计接口 500')
  })

  it('fetchDevices 失败：notification.error 提示', async () => {
    playbackPort.getAll.mockRejectedValue(new Error('设备接口超时'))
    const view = useSplMapping()

    await view.fetchDevices()

    expect(notifications.error).toHaveBeenCalledWith('获取设备列表失败: 设备接口超时')
  })
})
