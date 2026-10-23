/**
 * INT-1628：useDeviceManagement 导入导出接线（设备页签 → 三资源端点）
 *
 * 覆盖：
 * 1) 导入弹窗注入真实 importAction，导入成功回调刷新列表/统计；
 * 2) 导出范围由页面给到的勾选/筛选 id 集合生成（选中/筛选为空时置灰），
 *    选中导出把 ids 传给后端白名单；
 * 3) 页签 → 端口的映射不串资源（测试/播放/API）；
 * 4) 取消不刷新、不提示成功。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  notification: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  devicesGetAll: vi.fn(),
  devicesImport: vi.fn(),
  devicesExport: vi.fn(),
  playbackGetAll: vi.fn(),
  playbackImport: vi.fn(),
  playbackExport: vi.fn(),
  apisGetAll: vi.fn(),
  apisImport: vi.fn(),
  apisExport: vi.fn(),
  downloadBlob: vi.fn(),
}))

vi.mock('@/composables/device/devicesPort', () => ({
  devicesPort: {
    getAll: mocks.devicesGetAll,
    importFile: mocks.devicesImport,
    exportFile: mocks.devicesExport,
  },
}))

vi.mock('@/composables/device/playbackPort', () => ({
  playbackPort: {
    getAll: mocks.playbackGetAll,
    importFile: mocks.playbackImport,
    exportFile: mocks.playbackExport,
  },
}))

vi.mock('@/composables/apiTest/apisPort', () => ({
  apisPort: {
    getAll: mocks.apisGetAll,
    importFile: mocks.apisImport,
    exportFile: mocks.apisExport,
  },
}))

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal, close: vi.fn() }),
}))

vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => mocks.notification,
}))

vi.mock('@/utils/utils', () => ({
  downloadBlob: mocks.downloadBlob,
  generateDeviceFields: () => [],
}))

import { useDeviceManagement } from '../useDeviceManagement'
import { DeviceTabType } from '@/domain/enums'

type DeviceManagement = ReturnType<typeof useDeviceManagement>

/** 在组件上下文内使用 composable（生命周期钩子需要实例） */
function setupComposable(onDevicesChanged = vi.fn().mockResolvedValue(undefined)) {
  let management!: DeviceManagement
  const Host = defineComponent({
    setup() {
      management = useDeviceManagement(DeviceTabType.TEST, onDevicesChanged)
      return () => null
    },
  })
  const wrapper = mount(Host)
  return { management, wrapper, onDevicesChanged }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.devicesGetAll.mockResolvedValue({ items: [] })
  mocks.playbackGetAll.mockResolvedValue([])
  mocks.apisGetAll.mockResolvedValue([])
})

describe('INT-1628 设备导入接线', () => {
  it('导入弹窗注入真实 importAction；成功后刷新列表并提示计数', async () => {
    const report = { importedCount: 1, updatedCount: 2, skippedCount: 0, errors: [] }
    mocks.openModal.mockResolvedValueOnce({ mode: 'import', result: report })
    mocks.devicesImport.mockResolvedValueOnce(report)

    const { management, wrapper, onDevicesChanged } = setupComposable()
    await flushPromises()

    await management.importDevices(DeviceTabType.TEST)
    await flushPromises()

    const props = mocks.openModal.mock.calls[0][1]
    expect(props).toMatchObject({ mode: 'import', title: '导入测试设备' })
    expect(typeof props.importAction).toBe('function')
    expect(props.resultNote).toBe('状态以本环境为准')

    const file = new File(['{}'], 'devices.json')
    await props.importAction(file)
    expect(mocks.devicesImport).toHaveBeenCalledWith(file)

    await props.onImported(report)
    expect(mocks.devicesGetAll).toHaveBeenCalled()
    expect(onDevicesChanged).toHaveBeenCalled()

    expect(mocks.notification.success).toHaveBeenCalledWith('导入完成：成功 1 个，更新 2 个，跳过 0 个')
    wrapper.unmount()
  })

  it('取消导入（open 返回 null）不刷新、不提示成功', async () => {
    mocks.openModal.mockResolvedValueOnce(null)
    const { management, wrapper } = setupComposable()
    await flushPromises()
    mocks.devicesGetAll.mockClear()

    await management.importDevices(DeviceTabType.TEST)
    await flushPromises()

    expect(mocks.notification.success).not.toHaveBeenCalled()
    expect(mocks.devicesGetAll).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('页签映射到各自端点：API 页签导入走 /apis/import 端口', async () => {
    mocks.openModal.mockResolvedValueOnce(null)
    const { management, wrapper } = setupComposable()
    await flushPromises()

    await management.importDevices(DeviceTabType.API)
    const props = mocks.openModal.mock.calls[0][1]
    expect(props.title).toBe('导入测试API')
    await props.importAction(new File(['{}'], 'apis.json'))
    expect(mocks.apisImport).toHaveBeenCalled()
    expect(mocks.devicesImport).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('INT-1628 设备导出接线', () => {
  it('全部导出：不带 ids；文件名用响应头解析结果下载', async () => {
    mocks.openModal.mockResolvedValueOnce({ mode: 'export', result: { filename: 'test_devices_1.json' } })
    mocks.devicesExport.mockResolvedValueOnce({ blob: new Blob(['{}']), filename: 'test_devices_1.json' })

    const { management, wrapper } = setupComposable()
    await flushPromises()
    await management.exportDevices(DeviceTabType.TEST)
    await flushPromises()

    const props = mocks.openModal.mock.calls[0][1]
    expect(props).toMatchObject({ mode: 'export', title: '导出测试设备', supportedFormats: ['json', 'excel'] })
    expect(props.exportRanges.map((range: any) => range.value)).toEqual(['all', 'selected', 'filtered'])
    // 无勾选/无筛选时两个范围置灰，不提供无法执行的选项
    expect(props.exportRanges[1].disabled).toBe(true)
    expect(props.exportRanges[2].disabled).toBe(true)

    await props.exportAction({ format: 'json', range: 'all' })
    expect(mocks.devicesExport).toHaveBeenCalledWith({ format: 'json', ids: undefined })
    expect(mocks.downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'test_devices_1.json')
    expect(mocks.notification.success).toHaveBeenCalledWith('已导出：test_devices_1.json')
    wrapper.unmount()
  })

  it('选中导出：勾选 id 作为 ids 白名单传后端', async () => {
    mocks.openModal.mockResolvedValueOnce(null)
    mocks.devicesExport.mockResolvedValueOnce({ blob: new Blob(['{}']), filename: 'test_devices_2.json' })

    const { management, wrapper } = setupComposable()
    await flushPromises()
    await management.exportDevices(DeviceTabType.TEST, { selectedIds: [1, 2], filteredIds: [1, 2, 3] })
    await flushPromises()

    const props = mocks.openModal.mock.calls[0][1]
    expect(props.exportRanges[1].disabled).toBe(false)
    expect(props.exportRanges[1].label).toBe('选中数据（2 台）')
    expect(props.exportRanges[2].label).toBe('筛选后数据（3 台）')

    await props.exportAction({ format: 'excel', range: 'selected' })
    expect(mocks.devicesExport).toHaveBeenCalledWith({ format: 'excel', ids: ['1', '2'] })
    wrapper.unmount()
  })

  it('筛选后导出：传筛选结果完整 id 集合（不是当前页）', async () => {
    mocks.openModal.mockResolvedValueOnce(null)
    mocks.playbackExport.mockResolvedValueOnce({ blob: new Blob(['{}']), filename: 'playback.json' })

    const { management, wrapper } = setupComposable()
    await flushPromises()
    await management.exportDevices(DeviceTabType.PLAYBACK, { selectedIds: [], filteredIds: [7, 8, 9] })
    const props = mocks.openModal.mock.calls[0][1]
    expect(props.title).toBe('导出播放设备')
    await props.exportAction({ format: 'json', range: 'filtered' })
    expect(mocks.playbackExport).toHaveBeenCalledWith({ format: 'json', ids: ['7', '8', '9'] })
    expect(mocks.devicesExport).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
