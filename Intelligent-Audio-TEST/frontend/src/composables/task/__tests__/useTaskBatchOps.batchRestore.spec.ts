/**
 * INT-284：批量恢复任务前必须弹 BASIC_CONFIRM 确认（全站危险操作确认范式）
 *
 * 覆盖：确认后按选中 id 全量走 tasksPort.batchAction('restore')、清空选中并刷新、
 * 用户取消不执行恢复、无选中不弹窗。
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
  return { ops, selectedTasks, fetchTasks }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.openModal.mockResolvedValue(true)
})

describe('INT-284：批量恢复任务前弹确认', () => {
  it('确认后：全部选中 id 恢复、清空选中并刷新', async () => {
    const { ops, selectedTasks, fetchTasks } = setup(['11', '12', '13'])

    await ops.batchRestore()

    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.BASIC_CONFIRM,
      expect.objectContaining({
        title: '批量恢复任务',
        content: '确定要恢复选中的 3 个任务吗？',
        confirmText: '恢复',
      }),
    )
    expect(mocks.batchAction).toHaveBeenCalledTimes(1)
    expect(mocks.batchAction).toHaveBeenCalledWith('restore', ['11', '12', '13'])
    expect(selectedTasks.value.size).toBe(0)
    expect(fetchTasks).toHaveBeenCalledTimes(1)
  })

  it('用户取消确认：不执行恢复', async () => {
    mocks.openModal.mockResolvedValue(false)
    const { ops } = setup(['11', '12'])

    await ops.batchRestore()

    expect(mocks.batchAction).not.toHaveBeenCalled()
  })

  it('无选中任务：不弹窗直接返回', async () => {
    const { ops } = setup([])

    await ops.batchRestore()

    expect(mocks.openModal).not.toHaveBeenCalled()
    expect(mocks.batchAction).not.toHaveBeenCalled()
  })
})
