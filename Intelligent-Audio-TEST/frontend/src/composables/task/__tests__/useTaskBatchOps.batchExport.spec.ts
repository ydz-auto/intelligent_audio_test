/**
 * INT-202：任务批量导出必须导出全部选中任务（回归：曾只取 ids[0]）
 *
 * 覆盖：全量选中 id 走 dataTransferPort.exportTasks（INT-25 任务数据导出链，
 * 而非报告导出链）、导出选项透传、ZIP 下载命名、用户取消不导出、
 * 无选中不弹窗、导出失败通知。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  notification: {
    error: vi.fn(),
    warning: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
  },
  exportTasks: vi.fn(),
  batchAction: vi.fn(),
  mergeTasks: vi.fn(),
  batchCompare: vi.fn(),
  downloadBlob: vi.fn(),
}))

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal }),
  MODAL_TYPES: {
    IMPORT_EXPORT: 'importExport',
    DELETE_CONFIRM: 'deleteConfirm',
    BASIC_CONFIRM: 'basicConfirm',
  },
}))

vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => mocks.notification,
}))

vi.mock('@/composables/task/dataTransferPort', () => ({
  dataTransferPort: { exportTasks: mocks.exportTasks },
}))

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: {
    batchAction: mocks.batchAction,
    mergeTasks: mocks.mergeTasks,
  },
}))

vi.mock('@/composables/report/useReportComparison', () => ({
  batchCompare: mocks.batchCompare,
}))

vi.mock('@/utils/utils', () => ({
  downloadBlob: mocks.downloadBlob,
}))

import { useTaskBatchOps } from '../useTaskBatchOps'
import { MODAL_TYPES } from '@/composables/modal/useModal'

const setup = (selectedIds: Array<string | number>) => {
  const tasks = ref([])
  const selectedTasks = ref(new Set<string | number>(selectedIds))
  const fetchTasks = vi.fn().mockResolvedValue(undefined)
  const ops = useTaskBatchOps(tasks, selectedTasks, fetchTasks)
  return { ops, selectedTasks }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.openModal.mockResolvedValue({
    config: { format: 'zip', includeRefParams: true, includeAudios: false },
  })
  mocks.exportTasks.mockResolvedValue(new Blob(['zip-bytes']))
})

describe('INT-202：批量导出全部选中任务', () => {
  it('多选任务：全部 id 传入任务数据导出链并下载 ZIP', async () => {
    const { ops } = setup(['11', '12', '13'])

    await ops.batchExport()

    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.IMPORT_EXPORT,
      expect.objectContaining({ mode: 'export', title: '批量导出任务' }),
    )
    expect(mocks.exportTasks).toHaveBeenCalledTimes(1)
    const [idsArg, optionsArg] = mocks.exportTasks.mock.calls[0]
    expect(idsArg).toEqual(['11', '12', '13'])
    expect(optionsArg).toEqual({ includeRefParams: true, includeAudios: false })
    expect(mocks.downloadBlob).toHaveBeenCalledWith(
      expect.any(Blob),
      expect.stringMatching(/^task_export_\d{14}\.zip$/),
    )
  })

  it('弹窗高级选项透传（含音频文件）', async () => {
    mocks.openModal.mockResolvedValue({
      config: { format: 'zip', includeRefParams: true, includeAudios: true },
    })
    const { ops } = setup([7])

    await ops.batchExport()

    expect(mocks.exportTasks).toHaveBeenCalledWith([7], {
      includeRefParams: true,
      includeAudios: true,
    })
  })

  it('用户取消弹窗：不发起导出', async () => {
    mocks.openModal.mockResolvedValue(null)
    const { ops } = setup(['11', '12'])

    await ops.batchExport()

    expect(mocks.exportTasks).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('无选中任务：不弹窗直接返回', async () => {
    const { ops } = setup([])

    await ops.batchExport()

    expect(mocks.openModal).not.toHaveBeenCalled()
    expect(mocks.exportTasks).not.toHaveBeenCalled()
  })

  it('导出失败：通知错误且不下载', async () => {
    mocks.exportTasks.mockRejectedValue(new Error('network down'))
    const { ops } = setup(['11'])

    await expect(ops.batchExport()).resolves.toBeUndefined()

    expect(mocks.notification.error).toHaveBeenCalledWith('批量导出任务失败，请稍后重试')
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })
})
