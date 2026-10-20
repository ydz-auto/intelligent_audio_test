/**
 * INT-274：LogView 三个危险操作（清除日志/批量标记/导出日志）确认弹窗必须真正生效
 *
 * 缺陷：logView.ts 三处向模态传 `message` 键 + `onConfirm` 回调；ModalConfirm 只消费
 * `content` prop，GlobalModalContainer 确认分支只调 `props.onSave`，导致弹窗不显示定制
 * 确认文案；导出弹窗还传了 ImportExportModal 不消费的 formatOptions/rangeOptions/fields，
 * 且 onConfirm 收到的载荷是 { mode, config } 而非预期 { range, format }。
 *
 * 修复口径（对齐容器确认分支实际消费的契约）：统一 `content` + `onSave`；导出弹窗改传
 * ImportExportModal 实际消费的 supportedFormats/exportFields，onSave 从 result.config 映射
 * range/format。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  logsPort: {
    getAll: vi.fn(),
    getStats: vi.fn(),
    refresh: vi.fn(),
    mark: vi.fn(),
    clear: vi.fn(),
    export: vi.fn(),
  },
  algorithmPort: { getOptions: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/LogView' }),
}))

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal }),
}))

vi.mock('@/composables/modal/constants', () => ({
  MODAL_TYPES: {
    DELETE_CONFIRM: 'deleteConfirm',
    BASIC_CONFIRM: 'basicConfirm',
    IMPORT_EXPORT: 'importExport',
  },
}))

vi.mock('@/composables/task/logsPort', () => ({
  logsPort: mocks.logsPort,
}))

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: mocks.algorithmPort,
}))

import { useLogView } from '../logView'
import { MODAL_TYPES } from '@/composables/modal/constants'
import type { LogRow } from '@/domain'

const emptyPage = () => ({ items: [], total: 0, page: 1, perPage: 10, pages: 0 })
const emptyStats = () => ({ total: 0, debug: 0, info: 0, warning: 0, error: 0, critical: 0 })

const makeLog = (id: number, selected = false): LogRow => ({
  id,
  level: 'info',
  content: `log-${id}`,
  time: '10:00:00',
  mark: '',
  ...(selected ? { selected: true } : {}),
})

beforeEach(() => {
  vi.clearAllMocks()
  mocks.logsPort.getAll.mockResolvedValue(emptyPage())
  mocks.logsPort.getStats.mockResolvedValue(emptyStats())
  mocks.logsPort.refresh.mockResolvedValue({ items: [], count: 0, newCount: 0, lastId: 0 })
  mocks.algorithmPort.getOptions.mockResolvedValue([])
})

describe('INT-274 清除日志', () => {
  it('确认弹窗传 content（非 message）+ onSave，确认后调用 logsPort.clear 并刷新', async () => {
    const view = useLogView()

    view.clearLogs()

    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.DELETE_CONFIRM,
      expect.objectContaining({
        title: '确认清除',
        content: '确定要清除所有日志吗？此操作不可撤销。',
        confirmText: '确定清除',
        cancelText: '取消',
      }),
    )
    const props = mocks.openModal.mock.calls[0][1]
    expect(props).not.toHaveProperty('message')
    expect(props).not.toHaveProperty('onConfirm')
    expect(typeof props.onSave).toBe('function')

    // 模拟容器确认分支调用 onSave（GlobalModalContainer @confirm → props.onSave）
    await props.onSave()

    expect(mocks.logsPort.clear).toHaveBeenCalledTimes(1)
    expect(mocks.logsPort.getAll).toHaveBeenCalled()
  })
})

describe('INT-274 批量标记', () => {
  it('无选中日志：不弹窗直接返回', () => {
    const view = useLogView()
    view.logs.value = [makeLog(1), makeLog(2)]

    view.batchMarkLogs()

    expect(mocks.openModal).not.toHaveBeenCalled()
  })

  it('确认弹窗传 content + onSave，确认后按选中 id + 当前标记色调用 logsPort.mark', async () => {
    const view = useLogView()
    view.markColor.value = 'red'
    view.logs.value = [
      { ...makeLog(1), selected: true },
      { ...makeLog(2) },
      { ...makeLog(3), selected: true },
    ]

    view.batchMarkLogs()

    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.BASIC_CONFIRM,
      expect.objectContaining({
        title: '确认标记',
        content: '确定要标记选中的 2 条日志吗？',
        confirmText: '确定标记',
        cancelText: '取消',
      }),
    )
    const props = mocks.openModal.mock.calls[0][1]
    expect(props).not.toHaveProperty('message')
    expect(props).not.toHaveProperty('onConfirm')
    expect(typeof props.onSave).toBe('function')

    await props.onSave()

    expect(mocks.logsPort.mark).toHaveBeenCalledTimes(1)
    expect(mocks.logsPort.mark).toHaveBeenCalledWith([1, 3], 'red')
    // 本地选中行标记同步更新
    expect((view.logs.value[0] as any).mark).toBe('red')
    expect((view.logs.value[2] as any).mark).toBe('red')
  })
})

describe('INT-274 导出日志', () => {
  it('弹窗传 ImportExportModal 实际消费的 supportedFormats/exportFields + onSave（不再传无效键）', () => {
    const view = useLogView()
    view.logs.value = [makeLog(1)]

    view.exportLogs()

    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.IMPORT_EXPORT,
      expect.objectContaining({
        mode: 'export',
        title: '导出日志',
        supportedFormats: ['json', 'excel'],
      }),
    )
    const props = mocks.openModal.mock.calls[0][1]
    expect(Array.isArray(props.exportFields)).toBe(true)
    expect(props.exportFields[0]).toMatchObject({ key: 'time', defaultChecked: true })
    expect(props.exportFields.find((f: any) => f.key === 'context')).toMatchObject({ defaultChecked: false })
    // 旧无效键/回调口径全部移除
    expect(props).not.toHaveProperty('formatOptions')
    expect(props).not.toHaveProperty('rangeOptions')
    expect(props).not.toHaveProperty('fields')
    expect(props).not.toHaveProperty('onConfirm')
    expect(typeof props.onSave).toBe('function')
  })

  it('确认后 range=selected：logIds 只含选中行 + format 透传', async () => {
    const view = useLogView()
    view.logs.value = [
      { ...makeLog(1), selected: true },
      { ...makeLog(2) },
    ]

    view.exportLogs()
    const props = mocks.openModal.mock.calls[0][1]
    await props.onSave({ mode: 'export', config: { format: 'json', range: 'selected', fields: ['time'] } })

    expect(mocks.logsPort.export).toHaveBeenCalledTimes(1)
    const [exportArg] = mocks.logsPort.export.mock.calls[0]
    expect(exportArg.format).toBe('json')
    expect(exportArg.logIds).toBe('1')
  })

  it('确认后 range=all：不带 logIds，format 透传', async () => {
    const view = useLogView()
    view.logs.value = [{ ...makeLog(1), selected: true }]

    view.exportLogs()
    const props = mocks.openModal.mock.calls[0][1]
    await props.onSave({ mode: 'export', config: { format: 'excel', range: 'all' } })

    expect(mocks.logsPort.export).toHaveBeenCalledTimes(1)
    const [exportArg] = mocks.logsPort.export.mock.calls[0]
    expect(exportArg.format).toBe('excel')
    expect(exportArg.logIds).toBeUndefined()
  })
})
