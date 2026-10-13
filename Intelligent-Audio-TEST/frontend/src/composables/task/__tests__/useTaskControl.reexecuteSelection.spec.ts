/**
 * INT-302：重执行/重评估按用例+按维度选择（useTaskControl 接线单测）
 *
 * 覆盖（端口层 mock，http 层断言 wire 契约）：
 * - retryTask：REEXECUTE_OPTIONS 模态确认 → tasksPort.retry 携带 caseIds/mode；
 *   mode='all' 时不带 options（整任务语义零改动）；模态取消不发起请求；
 * - reevaluateTask：确认载荷 → tasksPort.reevaluate 携带 case_ids/dimension_ids/mode；
 *   mode='all'+维度全选（dimensionIds 空）时不带 selection（旧语义）；selected 仅带选中集。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  notification: {
    error: vi.fn(),
    warning: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
  },
  retry: vi.fn(),
  reevaluate: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal }),
  MODAL_TYPES: {
    BASIC_CONFIRM: 'basicConfirm',
    REEXECUTE_OPTIONS: 'reexecuteOptions',
    REEVALUATE: 'reevaluate',
  },
}))

vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => mocks.notification,
}))

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: {
    retry: mocks.retry,
    reevaluate: mocks.reevaluate,
    control: vi.fn(),
    stop: vi.fn(),
    delete: vi.fn(),
    start: vi.fn(),
    update: vi.fn(),
  },
}))

vi.mock('@/composables/report/reportsPort', () => ({
  reportsPort: {},
}))

vi.mock('@/composables/report/useReportComparison', () => ({
  viewTaskReport: vi.fn(),
  regenerateTaskReport: vi.fn(),
}))

import { useTaskControl } from '../useTaskControl'

/** 构造 useTaskControl 最小夹具（fetchTasks 空实现，任务列表空） */
const setup = () => {
  const fetchTasks = vi.fn().mockResolvedValue(undefined)
  const ctl = useTaskControl(ref([]), fetchTasks)
  return ctl
}

describe('INT-302 retryTask 按用例选择', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mode=all：确认后 retry 不带 options（整任务语义零改动）', async () => {
    mocks.openModal.mockResolvedValueOnce({ mode: 'all', caseIds: [], dimensionIds: [] })
    mocks.retry.mockResolvedValueOnce({})
    const ctl = setup()

    await ctl.retryTask(9)

    expect(mocks.openModal).toHaveBeenCalledTimes(1)
    const [modalType, modalProps] = mocks.openModal.mock.calls[0]
    expect(modalType).toBe('reexecuteOptions')
    expect(modalProps.actionType).toBe('retry')
    expect(modalProps.taskId).toBe(9)

    expect(mocks.retry).toHaveBeenCalledTimes(1)
    expect(mocks.retry).toHaveBeenCalledWith(9, undefined)
  })

  it('mode=selected：确认后 retry 携带 caseIds + mode', async () => {
    mocks.openModal.mockResolvedValueOnce({ mode: 'selected', caseIds: ['c1', 'c2'], dimensionIds: [] })
    mocks.retry.mockResolvedValueOnce({})
    const ctl = setup()

    await ctl.retryTask(9)

    expect(mocks.retry).toHaveBeenCalledWith(9, { caseIds: ['c1', 'c2'], mode: 'selected' })
  })

  it('模态取消（resolve undefined）：不发起 retry 请求', async () => {
    mocks.openModal.mockResolvedValueOnce(undefined)
    const ctl = setup()

    await ctl.retryTask(9)

    expect(mocks.retry).not.toHaveBeenCalled()
  })
})

describe('INT-302 reevaluateTask 按用例+按维度选择', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('mode=all + 维度全选（dimensionIds 空）：reevaluate 不带 selection（旧语义）', async () => {
    mocks.openModal.mockResolvedValueOnce({ mode: 'all', caseIds: [], dimensionIds: [] })
    mocks.reevaluate.mockResolvedValueOnce({ data: { message: '已提交' } })
    const ctl = setup()

    await ctl.reevaluateTask(9)
    // 清掉轮询定时器，避免 fake timer 泄漏
    await vi.runAllTimersAsync()

    const [modalType, modalProps] = mocks.openModal.mock.calls[0]
    expect(modalType).toBe('reexecuteOptions')
    expect(modalProps.actionType).toBe('reevaluate')

    expect(mocks.reevaluate).toHaveBeenCalledTimes(1)
    expect(mocks.reevaluate).toHaveBeenCalledWith(9, 'all', false, undefined)
  })

  it('selected + 部分维度：reevaluate 携带 case_ids/dimension_ids/mode', async () => {
    mocks.openModal.mockResolvedValueOnce({ mode: 'selected', caseIds: ['c1'], dimensionIds: [7, 8] })
    mocks.reevaluate.mockResolvedValueOnce({ data: { message: '已提交' } })
    const ctl = setup()

    await ctl.reevaluateTask(9)
    await vi.runAllTimersAsync()

    expect(mocks.reevaluate).toHaveBeenCalledWith(9, 'all', false, {
      caseIds: ['c1'],
      dimensionIds: [7, 8],
      mode: 'selected',
    })
  })

  it('mode=failed_only + 维度全选：reevaluate_type 映射为 failed，无 selection', async () => {
    mocks.openModal.mockResolvedValueOnce({ mode: 'failed_only', caseIds: [], dimensionIds: [] })
    mocks.reevaluate.mockResolvedValueOnce({})
    const ctl = setup()

    await ctl.reevaluateTask(9)
    await vi.runAllTimersAsync()

    expect(mocks.reevaluate).toHaveBeenCalledWith(9, 'failed', false, undefined)
  })

  it('mode=failed_only + 部分维度：failed 与维度选择取交集（携带 dimensionIds）', async () => {
    mocks.openModal.mockResolvedValueOnce({ mode: 'failed_only', caseIds: [], dimensionIds: [7] })
    mocks.reevaluate.mockResolvedValueOnce({})
    const ctl = setup()

    await ctl.reevaluateTask(9)
    await vi.runAllTimersAsync()

    expect(mocks.reevaluate).toHaveBeenCalledWith(9, 'failed', false, {
      caseIds: [],
      dimensionIds: [7],
      mode: 'failed_only',
    })
  })
})
