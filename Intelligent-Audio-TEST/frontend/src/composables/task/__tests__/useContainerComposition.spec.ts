/**
 * INT-1832 · 规范 18 §2.3：挑选合并容器识别写死口径 —— composable 单测。
 *
 * 锁定四种 source 返回的落点：
 * - 200 且 groups 非空 → 容器（isContainer=true，来源/结果计数来自 groups.length / total）
 * - 200 且 groups=[]   → 仍是容器（关系行缺失异常态，组成区走「无来源记录」空态）
 * - 4xx（实测 400 / code:203，站内普通任务常态）→ 非容器，归一 null，静默
 * - 5xx / 网络中断     → 同上，归一 null（详情页绝不因可选增强区变错误页）
 * 另锁：无 taskId 不发请求；任务切换时过期响应不得覆盖新任务判定。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({ getSource: vi.fn(), getOne: vi.fn() }))

vi.mock('@/infrastructure/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api')>()
  return {
    ...actual,
    cherryPickApi: { ...actual.cherryPickApi, getSource: mocks.getSource },
    tasksApi: { ...actual.tasksApi, getOne: mocks.getOne },
  }
})

import {
  clearContainerCompositionCache,
  useContainerComposition,
  useContainerTraceComposition,
} from '../useContainerComposition'

const sourcePayload = (overrides: Record<string, unknown> = {}) => ({
  taskId: 580,
  isCherryPick: true,
  total: 5,
  groups: [
    {
      sourceTaskId: 384,
      sourceTaskName: 'E2E测试任务_2026/9/21',
      results: [{ id: 1, resultId: 3792 }, { id: 2, resultId: 3796 }],
    },
    {
      sourceTaskId: 419,
      sourceTaskName: '小艺拒识E2E测试任务_2026/10/13',
      results: [{ id: 3, resultId: 5714 }, { id: 4, resultId: 5715 }, { id: 5, resultId: 5716 }],
    },
  ],
  ...overrides,
})

beforeEach(() => {
  vi.clearAllMocks()
  clearContainerCompositionCache()
})

describe('useContainerComposition 容器识别（INT-1832）', () => {
  it('200 且 groups 非空 → 容器，计数取 groups.length / total', async () => {
    mocks.getSource.mockResolvedValue(sourcePayload())
    const state = useContainerComposition(ref(580))
    await flushPromises()

    expect(mocks.getSource).toHaveBeenCalledWith(580)
    expect(state.isContainer.value).toBe(true)
    expect(state.sourceTaskCount.value).toBe(2)
    expect(state.sourceResultCount.value).toBe(5)
    expect(state.source.value?.groups[0].sourceTaskName).toBe('E2E测试任务_2026/9/21')
    expect(state.loading.value).toBe(false)
    expect(state.settled.value).toBe(true)
  })

  it('200 且 groups=[] 且 is_cherry_pick=true → 仍判定容器（关系行缺失异常态，不降级为非容器）', async () => {
    mocks.getSource.mockResolvedValue(sourcePayload({ groups: [], total: 0, isCherryPick: true }))
    const state = useContainerComposition(ref(503))
    await flushPromises()

    expect(state.isContainer.value).toBe(true)
    expect(state.sourceTaskCount.value).toBe(0)
    expect(state.sourceResultCount.value).toBe(0)
  })

  it('200 且 is_cherry_pick=false（站内普通任务真实返回）→ 非容器静默', async () => {
    // 实测真实库栈：GET /tasks/cherry-picks/{普通任务}/source → 200 {is_cherry_pick:false,total:0,groups:[]}
    mocks.getSource.mockResolvedValue({ taskId: 526, isCherryPick: false, total: 0, groups: [] })
    const state = useContainerComposition(ref(526))
    await flushPromises()

    expect(state.source.value).toBeNull()
    expect(state.isContainer.value).toBe(false)
  })

  it('200 且 groups 非空但 is_cherry_pick=false（契约矛盾）→ 以关系行为准，判定容器', async () => {
    mocks.getSource.mockResolvedValue(sourcePayload({ isCherryPick: false }))
    const state = useContainerComposition(ref(580))
    await flushPromises()

    expect(state.isContainer.value).toBe(true)
  })

  it('4xx（400 / code:203）→ 非容器静默：归一 null、不冒泡', async () => {
    const apiError: any = new Error('任务不是挑选合并容器')
    apiError.code = 203
    mocks.getSource.mockRejectedValue(apiError)

    const state = useContainerComposition(ref(42))
    await flushPromises()

    expect(state.source.value).toBeNull()
    expect(state.isContainer.value).toBe(false)
    expect(state.sourceTaskCount.value).toBe(0)
    expect(state.loading.value).toBe(false)
    expect(state.settled.value).toBe(true)
  })

  it('5xx → 同 4xx 静默归一 null（详情页不因可选增强区变错误页）', async () => {
    mocks.getSource.mockRejectedValue(new Error('500 Internal Server Error'))
    const state = useContainerComposition(ref(43))
    await flushPromises()

    expect(state.source.value).toBeNull()
    expect(state.isContainer.value).toBe(false)
  })

  it('网络中断 → 静默归一 null', async () => {
    mocks.getSource.mockRejectedValue(new TypeError('Failed to fetch'))
    const state = useContainerComposition(ref(44))
    await flushPromises()

    expect(state.source.value).toBeNull()
    expect(state.isContainer.value).toBe(false)
  })

  it('200 但契约缺 groups（异常载荷）→ 归一 null，不当作容器渲染空信息头', async () => {
    mocks.getSource.mockResolvedValue({ taskId: 45, isCherryPick: true, total: 0 })
    const state = useContainerComposition(ref(45))
    await flushPromises()

    expect(state.isContainer.value).toBe(false)
  })

  it('无 taskId → 不发请求，判定直接落非容器', async () => {
    const state = useContainerComposition(ref(null))
    await flushPromises()

    expect(mocks.getSource).not.toHaveBeenCalled()
    expect(state.source.value).toBeNull()
    expect(state.settled.value).toBe(true)
  })

  it('任务切换：旧任务迟到的响应不得覆盖新任务的判定', async () => {
    let resolveFirst: (value: unknown) => void = () => {}
    mocks.getSource
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce(sourcePayload({ taskId: 999, total: 1, groups: [
        { sourceTaskId: 1, sourceTaskName: '新任务来源', results: [{ id: 1, resultId: 1 }] },
      ] }))

    const taskId = ref<string | number | null>(580)
    const state = useContainerComposition(taskId)
    taskId.value = 999
    await flushPromises()

    expect(state.sourceResultCount.value).toBe(1)

    // 旧任务响应此刻才返回：必须被丢弃
    resolveFirst(sourcePayload({ total: 5 }))
    await flushPromises()

    expect(state.sourceTaskCount.value).toBe(1)
    expect(state.sourceResultCount.value).toBe(1)
  })
})

// ===== INT-1834 · 落点③ 行展开：组成模型 + 按 taskId 缓存（规范 18 §4.3） =====

const detailPayload = (overrides: Record<string, unknown> = {}) => ({
  id: 580,
  name: '容器580',
  status: 'completed',
  cases: [
    { caseId: 'C1', name: 'JS177 拒识用例', groupName: '拒识', tags: ['标签A'], executionStatus: 'completed', evaluationStatus: 'completed' },
  ],
  devices: [{ id: 9, name: 'pura90小艺' }],
  apis: [],
  ...overrides,
})

describe('useContainerTraceComposition 行展开补拉与缓存（INT-1834）', () => {
  it('首次展开：source + 详情各 1 次，条目 join 用例名 / 设备名 / 分组 / 标签', async () => {
    mocks.getSource.mockResolvedValue({
      taskId: 580, isCherryPick: true, total: 1,
      groups: [{ sourceTaskId: 419, sourceTaskName: '来源任务', results: [
        { id: 5714, resultId: 5714, sourceCaseId: 'C1', sourceDeviceId: 9, missing: false },
      ] }],
    })
    mocks.getOne.mockResolvedValue(detailPayload())

    const state = useContainerTraceComposition(ref(580))
    await flushPromises()

    expect(mocks.getSource).toHaveBeenCalledWith(580)
    expect(mocks.getOne).toHaveBeenCalledWith(580)
    expect(state.error.value).toBe(false)
    expect(state.loading.value).toBe(false)
    const model = state.model.value
    expect(model?.taskCount).toBe(1)
    expect(model?.resultCount).toBe(1)
    expect(model?.entries).toHaveLength(1)
    expect(model?.entries[0].sourceCaseName).toBe('JS177 拒识用例')
    expect(model?.entries[0].sourceDeviceName).toBe('pura90小艺')
    expect(model?.entries[0].groupName).toBe('拒识')
    expect(model?.entries[0].tags).toEqual(['标签A'])
  })

  it('收起再展开（新实例同 taskId）：命中缓存，零新请求', async () => {
    mocks.getSource.mockResolvedValue({
      taskId: 580, isCherryPick: true, total: 1,
      groups: [{ sourceTaskId: 419, sourceTaskName: '来源任务', results: [{ id: 1, resultId: 1, sourceCaseId: 'C1' }] }],
    })
    mocks.getOne.mockResolvedValue(detailPayload())

    useContainerTraceComposition(ref(580))
    await flushPromises()
    expect(mocks.getOne).toHaveBeenCalledTimes(1)

    const again = useContainerTraceComposition(ref(580))
    await flushPromises()

    expect(mocks.getSource).toHaveBeenCalledTimes(1)
    expect(mocks.getOne).toHaveBeenCalledTimes(1)
    expect(again.model.value?.entries).toHaveLength(1)
    expect(again.loading.value).toBe(false)
  })

  it('换行展开：不同 taskId 各补拉 1 次', async () => {
    mocks.getSource.mockImplementation(async (id: number) => ({
      taskId: id, isCherryPick: true, total: 1,
      groups: [{ sourceTaskId: id, sourceTaskName: `来源${id}`, results: [{ id, resultId: id, sourceCaseId: 'C1' }] }],
    }))
    mocks.getOne.mockImplementation(async (id: number) => detailPayload({ id }))

    useContainerTraceComposition(ref(580))
    await flushPromises()
    useContainerTraceComposition(ref(581))
    await flushPromises()

    expect(mocks.getOne).toHaveBeenCalledTimes(2)
    expect(mocks.getOne).toHaveBeenNthCalledWith(1, 580)
    expect(mocks.getOne).toHaveBeenNthCalledWith(2, 581)
  })

  it('补拉失败：error=true 且不写缓存；retry 重新请求成功后落缓存', async () => {
    mocks.getSource.mockResolvedValue({
      taskId: 580, isCherryPick: true, total: 1,
      groups: [{ sourceTaskId: 419, sourceTaskName: '来源任务', results: [{ id: 1, resultId: 1, sourceCaseId: 'C1' }] }],
    })
    mocks.getOne
      .mockRejectedValueOnce(new Error('500'))
      .mockResolvedValueOnce(detailPayload())

    const state = useContainerTraceComposition(ref(580))
    await flushPromises()

    expect(state.error.value).toBe(true)
    expect(state.model.value).toBeNull()

    await state.retry()
    await flushPromises()

    expect(mocks.getOne).toHaveBeenCalledTimes(2)
    expect(state.error.value).toBe(false)
    expect(state.model.value?.entries).toHaveLength(1)
  })

  it('同一 taskId 并发加载合并为一次请求', async () => {
    let resolveSource: (v: unknown) => void = () => {}
    mocks.getSource.mockImplementationOnce(() => new Promise((resolve) => { resolveSource = resolve }))
    mocks.getOne.mockResolvedValue(detailPayload())

    const a = useContainerTraceComposition(ref(580))
    const b = useContainerTraceComposition(ref(580))
    await flushPromises()

    resolveSource({ taskId: 580, isCherryPick: true, total: 0, groups: [] })
    await flushPromises()

    expect(mocks.getSource).toHaveBeenCalledTimes(1)
    expect(mocks.getOne).toHaveBeenCalledTimes(1)
    expect(a.model.value).not.toBeNull()
    expect(b.model.value).not.toBeNull()
  })
})
