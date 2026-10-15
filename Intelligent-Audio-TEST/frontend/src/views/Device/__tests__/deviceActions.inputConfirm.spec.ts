/**
 * INT-286：Device 装卸应用参数收集回归（window.prompt → INPUT_CONFIRM 表单模态）。
 *
 * 锁定口径：
 * - install_app/uninstall_app 打开 INPUT_CONFIRM（不再弹 window.prompt、无二次 BASIC_CONFIRM）
 * - 确认载荷经 trim 后随 control 下发（file_path / package_name）
 * - 用户取消（open reject）或空值 → 不下发 control
 * - validate 拒绝含空白字符的路径/包名
 * - 无参操作（connect 等）仍走原 BASIC_CONFIRM 确认链路
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const ports = vi.hoisted(() => ({
  control: vi.fn(),
  batchAction: vi.fn(),
  healthCheck: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())
const notifications = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const fetchAllDevices = vi.hoisted(() => vi.fn())

vi.mock('../../../composables/device/devicesPort', () => ({ devicesPort: ports }))
vi.mock('../../../composables/device/playbackPort', () => ({ playbackPort: { checkStatus: vi.fn(), stopTest: vi.fn() } }))
vi.mock('../../../composables/apiTest/apisPort', () => ({ apisPort: { testConnection: vi.fn(), stopTest: vi.fn() } }))
vi.mock('../../../composables/algorithm/algorithmPort', () => ({ algorithmPort: { getOptions: vi.fn() } }))
vi.mock('../../../composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('../deviceFetching', () => ({ fetchAllDevices }))
vi.mock('../deviceState', () => ({
  activeTab: ref('test'),
  dropdowns: ref({ batchDropdown: false, importExportDropdown: false }),
  groupManagerVisible: ref(false),
  searchQuery: ref(''),
  statusFilter: ref('all'),
  playbackTypeFilter: ref('all'),
  algorithmTypeFilter: ref('all'),
  algorithmFilter: ref('all'),
  selectedDevices: ref([]),
  testDevices: ref([]),
  playbackDevices: ref([]),
  apiDevices: ref([]),
  isScanning: ref(false),
  scanProgress: ref(0),
  scanStatus: ref(''),
  scanResults: ref([]),
  algorithmTypeOptions: ref([]),
  getDeviceManagement: () => ({ modalManager: { open: modalOpen } }),
}))

import { handleDeviceOperate } from '../deviceActions'
import { MODAL_TYPES } from '../../../composables/modal/constants'

beforeEach(() => {
  vi.clearAllMocks()
  ports.control.mockResolvedValue({})
  fetchAllDevices.mockResolvedValue(undefined)
})

describe('handleDeviceOperate（INT-286 装卸应用表单模态）', () => {
  it('install_app：打开 INPUT_CONFIRM，确认载荷 trim 后随 control 下发 file_path，且不弹 BASIC_CONFIRM', async () => {
    modalOpen.mockImplementation((type: string) => {
      expect(type).toBe(MODAL_TYPES.INPUT_CONFIRM)
      return Promise.resolve({ value: ' /opt/demo.apk ' })
    })

    await handleDeviceOperate('dev-1', 'install_app')

    expect(modalOpen).toHaveBeenCalledTimes(1)
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.INPUT_CONFIRM, expect.objectContaining({
      title: '安装应用',
      label: '服务器侧安装包路径（APK/HAP）',
    }))
    expect(ports.control).toHaveBeenCalledWith('dev-1', 'install_app', { file_path: '/opt/demo.apk' })
    expect(modalOpen.mock.calls.some(([type]) => type === MODAL_TYPES.BASIC_CONFIRM)).toBe(false)
  })

  it('install_app：用户取消（reject）→ 不下发 control', async () => {
    modalOpen.mockRejectedValue(new Error('cancel'))

    await handleDeviceOperate('dev-1', 'install_app')

    expect(ports.control).not.toHaveBeenCalled()
  })

  it('install_app：确认值为空白 → 视同取消，不下发', async () => {
    modalOpen.mockResolvedValue({ value: '   ' })

    await handleDeviceOperate('dev-1', 'install_app')

    expect(ports.control).not.toHaveBeenCalled()
  })

  it('install_app：validate 拒绝含空白字符的路径', async () => {
    let validate: ((v: string) => string | null) | undefined
    modalOpen.mockImplementation((_type: string, props: any) => {
      validate = props.validate
      return Promise.resolve({ value: '/opt/a b.apk' })
    })

    await handleDeviceOperate('dev-1', 'install_app')

    expect(validate).toBeDefined()
    expect(validate!('/opt/a b.apk')).toBe('路径不能包含空白字符')
    expect(validate!('/opt/a_b.apk')).toBeNull()
  })

  it('uninstall_app：INPUT_CONFIRM danger 标红 + 包名校验，确认载荷随 control 下发 package_name', async () => {
    modalOpen.mockResolvedValue({ value: ' com.demo.app ' })

    await handleDeviceOperate('dev-2', 'uninstall_app')

    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.INPUT_CONFIRM, expect.objectContaining({
      title: '卸载应用',
      danger: true,
    }))
    expect(ports.control).toHaveBeenCalledWith('dev-2', 'uninstall_app', { package_name: 'com.demo.app' })
  })

  it('uninstall_app：validate 拒绝含空白字符的包名', async () => {
    let validate: ((v: string) => string | null) | undefined
    modalOpen.mockImplementation((_type: string, props: any) => {
      validate = props.validate
      return Promise.reject(new Error('cancel'))
    })

    await handleDeviceOperate('dev-2', 'uninstall_app')

    expect(validate).toBeDefined()
    expect(validate!('com.demo app')).toBe('包名不能包含空白字符')
    expect(validate!('com.demo.app')).toBeNull()
  })

  it('connect（无参操作）：仍走 BASIC_CONFIRM 确认链路，确认后无 params 下发', async () => {
    // BASIC_CONFIRM 链路经 onConfirm/onCancel 回调驱动（GlobalModalContainer v-bind 契约）
    modalOpen.mockImplementation((type: string, props: any) => {
      expect(type).toBe(MODAL_TYPES.BASIC_CONFIRM)
      props.onConfirm()
      return Promise.resolve({ confirmed: true })
    })

    await handleDeviceOperate('dev-3', 'connect')

    expect(ports.control).toHaveBeenCalledWith('dev-3', 'connect', undefined)
  })

  it('connect：BASIC_CONFIRM 取消（onCancel）→ 不下发', async () => {
    modalOpen.mockImplementation((_type: string, props: any) => {
      props.onCancel()
      return Promise.resolve()
    })

    await handleDeviceOperate('dev-3', 'connect')

    expect(ports.control).not.toHaveBeenCalled()
  })
})
