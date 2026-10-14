/**
 * INT-282 验收：startApiTask 未勾选用例 → 按筛选拉全量回退（useTaskExecution 接线单测）。
 *
 * 缺陷回归：实装 TestFlow 迁移时丢失基线 V9.7.10 apiTest.ts:413-422 的
 * 「selectedTestCaseIds 为空 → fetchCaseIdsByFilter 拉全量再建任务」分支，
 * 空选择直接告警中止，大批量测试被迫逐个勾选。修复后：
 * - 未勾选 → store.fetchCaseIdsByFilter({ testType:'api', algorithmType }) 圈定全量；
 * - 圈定为空 → 告警「当前筛选条件下没有可用的测试用例…」并中止，不发创建请求；
 * - 已勾选 → 行为不变，仍按勾选集创建；
 * - 载荷显式携带 type:'api'（基线契约兼容留痕）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const mocks = vi.hoisted(() => ({
  fetchCaseIdsByFilter: vi.fn(),
  create: vi.fn(),
  start: vi.fn(),
}))

vi.mock('../../../store/testCaseStore', () => ({
  useTestCaseStore: () => ({
    fetchCaseIdsByFilter: mocks.fetchCaseIdsByFilter,
  }),
}))

vi.mock('../../task/tasksPort', () => ({
  tasksPort: {
    create: mocks.create,
    start: mocks.start,
  },
}))

import { useTaskExecution } from '../useTaskExecution'
import { TestType } from '../../../domain/enums'

/** 构造 API 模式 useTaskExecution 最小夹具 */
const buildFlow = (overrides: {
  selectedTestCaseIds?: (string | number)[]
  selectedAPIIds?: (string | number)[]
  apis?: any[]
  selectedAlgorithmType?: string | null
}) => {
  return useTaskExecution({
    testType: TestType.API,
    currentTaskId: ref<string | number | null>(null),
    taskName: ref('API测试任务'),
    selectedAlgorithmType: ref<string | null>(overrides.selectedAlgorithmType ?? 'voice_llm'),
    concurrentTasks: ref(5),
    selectedTestCaseIds: ref<(string | number)[]>(overrides.selectedTestCaseIds ?? []),
    selectedDeviceIds: ref<(string | number)[]>([]),
    e2eTestCases: ref<any[]>([]),
    selectedAPIIds: ref<(string | number)[]>(overrides.selectedAPIIds ?? [3]),
    apis: ref<any[]>(overrides.apis ?? [{ id: 3, name: 'voice-llm API', status: 'online', maxConcurrent: 5 }]),
    testCaseGroups: ref<Record<string, any[]>>({}),
    resetProgress: vi.fn(),
    associatedCases: ref<any[]>([]),
    totalTestCases: ref(0),
    pendingTests: ref(0),
    estimatedTime: ref(''),
    expectedCompleteTime: ref(''),
    addLog: vi.fn(),
  })
}

describe('INT-282：startApiTask 全量回退分支', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('未勾选用例 → fetchCaseIdsByFilter({ testType:"api", algorithmType }) 圈定全量并创建任务', async () => {
    mocks.fetchCaseIdsByFilter.mockResolvedValueOnce(['a1', 'a2', 'a3'])
    mocks.create.mockResolvedValueOnce({ id: 42 })
    mocks.start.mockResolvedValueOnce({})

    const flow = buildFlow({})
    const started = await flow.startApiTask()

    expect(started).toBe(true)
    expect(mocks.fetchCaseIdsByFilter).toHaveBeenCalledWith({
      testType: 'api',
      algorithmType: 'voice_llm',
    })
    // 载荷：全量 caseIds + 显式 type:'api'（基线契约兼容留痕）
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      type: 'api',
      caseIds: ['a1', 'a2', 'a3'],
    }))
  })

  it('筛选圈定为空 → 告警中止，不发起创建请求', async () => {
    mocks.fetchCaseIdsByFilter.mockResolvedValueOnce([])

    const flow = buildFlow({})
    const started = await flow.startApiTask()

    expect(started).toBe(false)
    expect(mocks.create).not.toHaveBeenCalled()
    expect(mocks.start).not.toHaveBeenCalled()
  })

  it('已勾选用例 → 不走筛选回退，按勾选集创建（行为不变）', async () => {
    mocks.create.mockResolvedValueOnce({ id: 7 })
    mocks.start.mockResolvedValueOnce({})

    const flow = buildFlow({ selectedTestCaseIds: ['c1', 'c2'] })
    const started = await flow.startApiTask()

    expect(started).toBe(true)
    expect(mocks.fetchCaseIdsByFilter).not.toHaveBeenCalled()
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      type: 'api',
      caseIds: ['c1', 'c2'],
    }))
  })

  it('未选在线 API → 即使全量圈定成功也中止', async () => {
    mocks.fetchCaseIdsByFilter.mockResolvedValueOnce(['a1'])

    const flow = buildFlow({ selectedAPIIds: [], apis: [] })
    const started = await flow.startApiTask()

    expect(started).toBe(false)
    expect(mocks.create).not.toHaveBeenCalled()
  })
})
