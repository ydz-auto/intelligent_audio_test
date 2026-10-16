/**
 * INT-203：WS 断开 → HTTP 进度接口兜底轮询
 *
 * 覆盖：断连启动轮询并应用 HTTP 进度、重连停止轮询并重新订阅任务房间、
 * 单次轮询失败不终止降级、终态停止、卸载防僵尸轮询（INT-100 同型竞态）、
 * 无任务不轮询、挂载即断连立即降级。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  connectionHandlers: [] as Array<(connected: boolean) => void>,
  onTaskProgress: vi.fn(),
  onTaskLog: vi.fn(),
  subscribeTask: vi.fn(),
  unsubscribeTask: vi.fn(),
  isConnected: vi.fn(),
  onConnectionChange: vi.fn(),
}))

vi.mock('@/composables/task/taskChannelPort', () => ({
  taskChannelPort: {
    onTaskProgress: mocks.onTaskProgress,
    onTaskLog: mocks.onTaskLog,
    subscribeTask: mocks.subscribeTask,
    unsubscribeTask: mocks.unsubscribeTask,
    isConnected: mocks.isConnected,
    onConnectionChange: mocks.onConnectionChange,
  },
}))

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: {
    getProgress: vi.fn(),
  },
}))

import { useTaskProgress } from '../useTaskProgress'
import { tasksPort } from '@/composables/task/tasksPort'
import type { TaskProgress } from '@/domain/model/taskProgress'

const POLL_MS = 5000

const mockedGetProgress = vi.mocked(tasksPort.getProgress)

const httpProgress = (overrides: Partial<TaskProgress> = {}): TaskProgress => ({
  taskId: '42',
  status: 'running',
  totalProgress: 50,
  completedCount: 2,
  inProgressCount: 0,
  executionFailedCount: 1,
  evaluationFailedCount: 0,
  totalCount: 4,
  currentCase: null,
  testCases: [],
  logs: [],
  apiResources: [],
  expectedTotalTime: null,
  expectedCompleteTime: null,
  usedTime: '',
  ...overrides,
})

const emitConnection = (connected: boolean) => {
  mocks.connectionHandlers.forEach(handler => handler(connected))
}

const mountWithProgress = (presetTaskId: string | number | null = null) => {
  let api!: ReturnType<typeof useTaskProgress>
  const currentTaskId = ref<string | number | null>(presetTaskId)
  const onCompleted = vi.fn()
  const Host = defineComponent({
    setup() {
      api = useTaskProgress({ currentTaskId, onCompleted })
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  return { wrapper, currentTaskId, api, onCompleted }
}

beforeEach(() => {
  vi.useFakeTimers()
  mocks.connectionHandlers.length = 0
  mocks.onTaskProgress.mockReset().mockReturnValue(() => {})
  mocks.onTaskLog.mockReset().mockReturnValue(() => {})
  mocks.subscribeTask.mockReset()
  mocks.unsubscribeTask.mockReset()
  mocks.isConnected.mockReset().mockReturnValue(true)
  mocks.onConnectionChange.mockReset().mockImplementation((handler: (connected: boolean) => void) => {
    mocks.connectionHandlers.push(handler)
    return () => {
      const index = mocks.connectionHandlers.indexOf(handler)
      if (index >= 0) mocks.connectionHandlers.splice(index, 1)
    }
  })
  mockedGetProgress.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('INT-203：HTTP 兜底轮询', () => {
  it('任务创建时断连：立即降级轮询并应用 HTTP 进度', async () => {
    mocks.isConnected.mockReturnValue(false)
    mockedGetProgress.mockResolvedValue(httpProgress())
    const { currentTaskId, api } = mountWithProgress()

    currentTaskId.value = '42'
    await vi.advanceTimersByTimeAsync(0)

    // 立即首轮（不等一个间隔）+ 应用计数
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
    expect(api.completedTests.value).toBe(2)
    expect(api.executionFailedTests.value).toBe(1)
    expect(api.progressPercentage.value).toBe(50)
    expect(api.isProgressPolling.value).toBe(true)

    // 周期续跑
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(mockedGetProgress).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(mockedGetProgress).toHaveBeenCalledTimes(3)
  })

  it('重连：停止轮询并重新订阅任务房间', async () => {
    mocks.isConnected.mockReturnValue(false)
    mockedGetProgress.mockResolvedValue(httpProgress())
    const { api } = mountWithProgress('42')

    // 挂载即断连 → 降级
    await vi.advanceTimersByTimeAsync(0)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
    const subscribeCallsAtMount = mocks.subscribeTask.mock.calls.length

    emitConnection(true)
    await vi.advanceTimersByTimeAsync(0)

    expect(api.isProgressPolling.value).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
    // task_log 走房间投递，重连后必须重新 subscribe_task
    expect(mocks.subscribeTask.mock.calls.length).toBe(subscribeCallsAtMount + 1)

    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
  })

  it('单次轮询失败：不终止降级，下个周期重试', async () => {
    mocks.isConnected.mockReturnValue(false)
    mockedGetProgress.mockRejectedValue(new Error('network down'))
    const { api } = mountWithProgress('42')

    await vi.advanceTimersByTimeAsync(0)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
    expect(api.isProgressPolling.value).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(mockedGetProgress).toHaveBeenCalledTimes(2)
    expect(api.isProgressPolling.value).toBe(true)
  })

  it('轮询到终态：停止轮询并触发 onCompleted（WS 丢失期间错过完成事件也能收尾）', async () => {
    mocks.isConnected.mockReturnValue(false)
    mockedGetProgress.mockResolvedValue(httpProgress({ status: 'completed' }))
    const { api, onCompleted } = mountWithProgress('42')

    await vi.advanceTimersByTimeAsync(0)

    expect(api.isProgressPolling.value).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
    expect(onCompleted).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
  })

  it('卸载防僵尸：在途轮询恢复后不再续跑', async () => {
    mocks.isConnected.mockReturnValue(false)
    let resolveProgress!: (v: TaskProgress) => void
    mockedGetProgress.mockImplementation(
      () => new Promise<TaskProgress>(resolve => { resolveProgress = resolve }),
    )
    const { wrapper, api } = mountWithProgress('42')

    await vi.advanceTimersByTimeAsync(0)
    expect(api.isProgressPolling.value).toBe(true)

    // 在途悬挂期间卸载
    wrapper.unmount()
    resolveProgress(httpProgress())
    await vi.advanceTimersByTimeAsync(0)

    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
  })

  it('无任务时不轮询', async () => {
    mountWithProgress(null)
    emitConnection(false)
    await vi.advanceTimersByTimeAsync(0)

    expect(mockedGetProgress).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('已连接时断连事件触发降级', async () => {
    mockedGetProgress.mockResolvedValue(httpProgress())
    const { api } = mountWithProgress('42')

    // 挂载时连接正常，不轮询
    expect(mocks.isConnected).toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(mockedGetProgress).not.toHaveBeenCalled()

    emitConnection(false)
    await vi.advanceTimersByTimeAsync(0)

    expect(api.isProgressPolling.value).toBe(true)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
  })

  it('断连-重连-再断连：第二次降级仍能启动轮询', async () => {
    mocks.isConnected.mockReturnValue(false)
    mockedGetProgress.mockResolvedValue(httpProgress())
    const { api } = mountWithProgress('42')

    // 第一次降级 → 重连停止
    await vi.advanceTimersByTimeAsync(0)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
    emitConnection(true)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.isProgressPolling.value).toBe(false)

    // 第二次断连必须重新降级（回归：generation 曾被误用作启动标志导致二次降级失效）
    emitConnection(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.isProgressPolling.value).toBe(true)
    expect(mockedGetProgress).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(mockedGetProgress).toHaveBeenCalledTimes(3)
  })
})

describe('INT-401 P1-3：重连在途 HTTP 兜底结果不丢弃（终态任务 socket 不重发进度）', () => {
  /** 触发最近一次挂载注册的 onTaskProgress 处理器（模拟 socket 进度事件） */
  const emitSocketProgress = (progress: TaskProgress) => {
    const handler = mocks.onTaskProgress.mock.calls.at(-1)?.[0]
    if (typeof handler === 'function') {
      void handler(progress)
    }
  }

  it('socket 在 HTTP 在途时重连：终态结果仍应用 → taskStatus 置为 completed', async () => {
    mocks.isConnected.mockReturnValue(false)
    let resolveProgress!: (v: TaskProgress) => void
    mockedGetProgress.mockImplementation(
      () => new Promise<TaskProgress>(resolve => { resolveProgress = resolve }),
    )
    const { api } = mountWithProgress('42')

    // 挂载即断连 → 首轮 HTTP 在途（getProgress 未返回）
    await vi.advanceTimersByTimeAsync(0)
    expect(api.isProgressPolling.value).toBe(true)

    // socket 在 HTTP 请求 await 期间重连（stopFallbackPolling → generation++），
    // 终态任务订阅后服务端不重发 task_progress —— 在途结果不得被 generation 丢弃
    emitConnection(true)
    await vi.advanceTimersByTimeAsync(0)

    resolveProgress(httpProgress({ status: 'completed' }))
    await vi.advanceTimersByTimeAsync(0)

    expect(api.taskStatus.value).toBe('completed')
    expect(api.isProgressPolling.value).toBe(false)
    // 应用后不再继续轮询
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(mockedGetProgress).toHaveBeenCalledTimes(1)
  })

  it('socket 已送达进度事件 → 在途 HTTP 旧结果丢弃（防终态→运行态回退）', async () => {
    mocks.isConnected.mockReturnValue(false)
    let resolveProgress!: (v: TaskProgress) => void
    mockedGetProgress.mockImplementation(
      () => new Promise<TaskProgress>(resolve => { resolveProgress = resolve }),
    )
    const { api } = mountWithProgress('42')

    await vi.advanceTimersByTimeAsync(0)
    expect(api.isProgressPolling.value).toBe(true)

    // socket 重连并送达较新的终态事件（权威源）
    emitConnection(true)
    emitSocketProgress(httpProgress({ status: 'completed' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(api.taskStatus.value).toBe('completed')

    // 在途旧 HTTP 结果返回 running：socket 已送达，不得覆盖回退
    resolveProgress(httpProgress({ status: 'running' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(api.taskStatus.value).toBe('completed')
  })
})
