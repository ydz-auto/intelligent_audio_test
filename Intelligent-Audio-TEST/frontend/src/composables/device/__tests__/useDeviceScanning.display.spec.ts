/**
 * INT-1105 设备 test 编辑态扫描选择器：空扫描时当前已注册设备按 serial 补进列表
 * （对齐 React INT-1029 编辑态可回填当前设备）。
 *
 * 场景：常驻后端无 ADB 设备（GET /test-devices/serials 返回空），编辑已注册测试设备时，
 * 选择器应把当前设备（按 serialNumber 匹配）以「当前设备」置顶展示，供用户选择回填。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { getAllFlatMock, playbackGetAllMock, playbackScanMock } = vi.hoisted(() => ({
  getAllFlatMock: vi.fn(),
  playbackGetAllMock: vi.fn(),
  playbackScanMock: vi.fn(),
}))

vi.mock('../devicesPort', () => ({
  devicesPort: { getAllFlat: getAllFlatMock },
  BATCH_LIST_PARAMS: { page: 1, per_page: 100 },
}))
vi.mock('../playbackPort', () => ({
  playbackPort: { getAll: playbackGetAllMock, scan: playbackScanMock },
}))

import { useDeviceScanning } from '../useDeviceScanning'

describe('useDeviceScanning.getTestDevicesDisplay 编辑态当前设备补齐（INT-1105）', () => {
  beforeEach(() => {
    getAllFlatMock.mockReset()
    playbackGetAllMock.mockReset()
    playbackScanMock.mockReset()
  })

  it('空扫描 + 编辑态：当前已注册测试设备按 serial 匹配置顶展示（isCurrent）', async () => {
    // 已注册测试设备（后端 DeviceItem：serialNumber 为设备序列号，id 为注册主键）
    getAllFlatMock.mockResolvedValue([
      { id: 6, name: 'pura90 测试设备', model: 'Harmony Device', system: 'harmony', systemVersion: 'harmony.base.v1', serialNumber: '6YF0126211000225', status: 'online', type: 'phone' },
    ])

    const { fetchAddedTestDevices, getTestDevicesDisplay } = useDeviceScanning()
    await fetchAddedTestDevices()

    // 编辑态当前设备 id = formData.serialNumber（CRUDFormModal displayDevices 口径）
    const display = getTestDevicesDisplay('6YF0126211000225', true)

    expect(display.length).toBe(1)
    expect(display[0].displayKey).toBe('6YF0126211000225')
    expect(display[0].name).toBe('pura90 测试设备')
    expect(display[0].isCurrent).toBe(true)
    expect(display[0].isAdded).toBe(true)
  })

  it('空扫描 + 编辑态：按 id/name 匹配的历史口径仍可用', async () => {
    getAllFlatMock.mockResolvedValue([
      { id: 7, name: '按ID匹配设备', model: 'M1', system: 'android', systemVersion: '12', serialNumber: 'SN-BYZID', status: 'offline', type: 'phone' },
    ])

    const { fetchAddedTestDevices, getTestDevicesDisplay } = useDeviceScanning()
    await fetchAddedTestDevices()

    // 播放/部分场景 currentDeviceId 可能为注册 id 或名称
    const byId = getTestDevicesDisplay('7', true)
    expect(byId.length).toBe(1)
    expect(byId[0].isCurrent).toBe(true)

    const byName = getTestDevicesDisplay('按ID匹配设备', true)
    expect(byName.length).toBe(1)
    expect(byName[0].isCurrent).toBe(true)
  })
})
