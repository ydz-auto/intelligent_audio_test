/**
 * INT-293：批量健康检查——PLAYBACK Tab 全量 checkStatus 只调一次；单设备失败不中断循环。
 *
 * 锁定契约：
 * 1. PLAYBACK Tab 下对 N 台选中设备只调用一次 playbackPort.checkStatus()（原实现在循环内
 *    N 次×全量查询），选中设备状态统一回写后清空选区；
 * 2. TEST/API Tab 下单设备检查失败仅计数并置 OFFLINE，不中断剩余设备（原实现整体抛错中断）；
 * 3. 有失败时给出「N 台设备检查失败」warning 提示。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DeviceStatus, DeviceTabType } from '@/domain/enums'

const ports = vi.hoisted(() => ({
  healthCheck: vi.fn(),
  testConnection: vi.fn(),
}))
const playback = vi.hoisted(() => ({ checkStatus: vi.fn() }))
const notifications = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const fetchAllDevices = vi.hoisted(() => vi.fn())

// hoisted 工厂中不可引用 import（初始化时序），用 { value } 形态的普通对象承担 ref 语义
//（deviceActions 仅读写 .value，不依赖 Vue 响应式追踪）
const state = vi.hoisted(() => ({
  activeTab: { value: 'playback' as string },
  selectedDevices: { value: [] as (string | number)[] },
  testDevices: { value: [] as any[] },
  playbackDevices: { value: [] as any[] },
  apiDevices: { value: [] as any[] },
}))

vi.mock('../../../composables/device/devicesPort', () => ({ devicesPort: { healthCheck: ports.healthCheck } }))
vi.mock('../../../composables/device/playbackPort', () => ({ playbackPort: playback }))
vi.mock('../../../composables/apiTest/apisPort', () => ({ apisPort: { testConnection: ports.testConnection } }))
vi.mock('../../../composables/algorithm/algorithmPort', () => ({ algorithmPort: { getOptions: vi.fn() } }))
vi.mock('../../../composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('../deviceFetching', () => ({ fetchAllDevices }))
vi.mock('../deviceState', () => ({
  activeTab: state.activeTab,
  dropdowns: { value: { batchDropdown: false, importExportDropdown: false } },
  groupManagerVisible: { value: false },
  searchQuery: { value: '' },
  statusFilter: { value: 'all' },
  playbackTypeFilter: { value: 'all' },
  algorithmTypeFilter: { value: 'all' },
  algorithmFilter: { value: 'all' },
  selectedDevices: state.selectedDevices,
  testDevices: state.testDevices,
  playbackDevices: state.playbackDevices,
  apiDevices: state.apiDevices,
  isScanning: { value: false },
  scanProgress: { value: 0 },
  scanStatus: { value: '' },
  scanResults: { value: [] },
  algorithmTypeOptions: { value: [] },
  getDeviceManagement: () => ({ modalManager: { open: vi.fn() } }),
}))

import { batchHealthCheck } from '../deviceActions'

beforeEach(() => {
  vi.clearAllMocks()
  ports.healthCheck.mockResolvedValue({})
  playback.checkStatus.mockResolvedValue([])
  state.activeTab.value = DeviceTabType.PLAYBACK
  state.selectedDevices.value = []
  state.testDevices.value = []
  state.playbackDevices.value = []
  state.apiDevices.value = []
})

describe('batchHealthCheck（INT-293）', () => {
  it('PLAYBACK Tab：checkStatus 仅调用一次，统一回写选中设备状态并清空选区', async () => {
    state.selectedDevices.value = ['p1', 'p2', 'p3']
    state.playbackDevices.value = [
      { id: 'p1', status: DeviceStatus.ONLINE },
      { id: 'p2', status: DeviceStatus.OFFLINE },
      { id: 'p3', status: DeviceStatus.OFFLINE },
    ]
    playback.checkStatus.mockResolvedValue([
      { id: 'p1', status: DeviceStatus.ONLINE },
      { id: 'p2', status: DeviceStatus.TESTING },
      { id: 'p3', status: DeviceStatus.OFFLINE },
    ])

    await batchHealthCheck()

    expect(playback.checkStatus).toHaveBeenCalledTimes(1)
    const byId = (id: string) => state.playbackDevices.value.find(d => d.id === id)!
    expect(byId('p2').status).toBe(DeviceStatus.TESTING)
    expect(byId('p3').status).toBe(DeviceStatus.OFFLINE)
    expect(state.selectedDevices.value).toEqual([])
    expect(notifications.warning).not.toHaveBeenCalled()
  })

  it('TEST Tab：单设备检查失败仅计数并置 OFFLINE，不中断剩余设备', async () => {
    state.activeTab.value = DeviceTabType.TEST
    state.selectedDevices.value = ['t1', 't2']
    state.testDevices.value = [
      { id: 't1', status: DeviceStatus.ONLINE },
      { id: 't2', status: DeviceStatus.ONLINE },
    ]
    ports.healthCheck.mockRejectedValueOnce(new Error('t1 检查超时'))
    ports.healthCheck.mockResolvedValueOnce({})

    await batchHealthCheck()

    expect(ports.healthCheck).toHaveBeenCalledTimes(2) // t1 失败后仍继续检查 t2
    const byId = (id: string) => state.testDevices.value.find(d => d.id === id)!
    expect(byId('t1').status).toBe(DeviceStatus.OFFLINE)
    expect(byId('t2').status).toBe(DeviceStatus.TESTING)
    expect(notifications.warning).toHaveBeenCalledWith('批量健康检查完成，1 台设备检查失败')
    expect(state.selectedDevices.value).toEqual([])
  })

  it('无选中设备时直接 warning 提示，不发起任何检查', async () => {
    state.activeTab.value = DeviceTabType.TEST
    state.selectedDevices.value = []

    await batchHealthCheck()

    expect(ports.healthCheck).not.toHaveBeenCalled()
    expect(playback.checkStatus).not.toHaveBeenCalled()
    expect(notifications.warning).toHaveBeenCalledWith('请先选择要检查的设备')
  })
})
