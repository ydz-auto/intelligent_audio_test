/**
 * useTaskEventsStream 单测：
 * - 无 sse:read 不建立订阅
 * - 订阅 TASK_EVENTS，状态迁移去抖后失效 ['tasks']；同签名进度事件不重复失效
 * - 非 task_progress 事件忽略
 */
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useTaskEventsStream } from '@/application/tasks/use-task-events-stream'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { SSE_EVENT_CHANNELS } from '@/infrastructure/realtime/sse'
import type { SseEvent } from '@/infrastructure/realtime/sse'
import { subscribeSharedSse } from '@/infrastructure/realtime/sse-bus'

vi.mock('@/infrastructure/realtime/sse', () => ({
  SSE_EVENT_CHANNELS: {
    TASK_EVENTS: 'task_events',
    CASE_EVENTS: 'case_events',
    DEVICE_EVENTS: 'device_events',
    REPORT_EVENTS: 'report_events',
    CONFIG_EVENTS: 'config_events',
  },
}))

vi.mock('@/infrastructure/realtime/sse-bus', () => ({
  subscribeSharedSse: vi.fn(),
}))

const subscribeMock = vi.mocked(subscribeSharedSse)

function makeUser(permissions: string[]) {
  return {
    id: '1',
    username: 'u',
    displayName: 'u',
    roleName: '',
    permissions,
  }
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries').mockResolvedValue()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { invalidateSpy, wrapper }
}

function progressEvent(
  taskId: number,
  status: string,
  executionStatus: string,
  evaluationStatus: string
): SseEvent {
  return {
    channel: SSE_EVENT_CHANNELS.TASK_EVENTS,
    eventType: 'task_progress',
    data: {
      task_id: String(taskId),
      status,
      execution_status: executionStatus,
      evaluation_status: evaluationStatus,
      completed_count: 1,
    },
    id: undefined,
  }
}

function getOptions() {
  return subscribeMock.mock.calls[0][0] as {
    channels: string[]
    onEvent: (event: SseEvent) => void
  }
}

describe('useTaskEventsStream', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    useAuthStore.setState({ user: makeUser(['sse:read']) })
    subscribeMock.mockReset()
    subscribeMock.mockReturnValue(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('无 sse:read 权限时不订阅', () => {
    useAuthStore.setState({ user: makeUser([]) })
    const { wrapper } = setup()

    renderHook(() => useTaskEventsStream(), { wrapper })

    expect(subscribeMock).not.toHaveBeenCalled()
  })

  it('订阅 TASK_EVENTS，仅在状态迁移时失效任务查询', () => {
    const { invalidateSpy, wrapper } = setup()
    renderHook(() => useTaskEventsStream(), { wrapper })

    expect(subscribeMock).toHaveBeenCalledTimes(1)
    const options = getOptions()
    expect(options.channels).toEqual([SSE_EVENT_CHANNELS.TASK_EVENTS])

    // 首次见到任务 → 失效一次；同状态重复事件不重复失效
    options.onEvent(progressEvent(474, 'running', 'running', 'pending'))
    options.onEvent(progressEvent(474, 'running', 'running', 'pending'))
    expect(invalidateSpy).not.toHaveBeenCalled()
    vi.advanceTimersByTime(400)
    expect(invalidateSpy).toHaveBeenCalledTimes(1)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['tasks'] })

    // 状态迁移（执行中 → 已完成）→ 再次失效
    options.onEvent(progressEvent(474, 'completed', 'completed', 'completed'))
    vi.advanceTimersByTime(400)
    expect(invalidateSpy).toHaveBeenCalledTimes(2)
  })

  it('评估状态推进同样触发失效', () => {
    const { invalidateSpy, wrapper } = setup()
    renderHook(() => useTaskEventsStream(), { wrapper })
    const options = getOptions()

    options.onEvent(progressEvent(475, 'completed', 'completed', 'evaluating'))
    vi.advanceTimersByTime(400)
    options.onEvent(progressEvent(475, 'completed', 'completed', 'completed'))
    vi.advanceTimersByTime(400)

    expect(invalidateSpy).toHaveBeenCalledTimes(2)
  })

  it('非 task_progress 事件不触发失效', () => {
    const { invalidateSpy, wrapper } = setup()
    renderHook(() => useTaskEventsStream(), { wrapper })

    getOptions().onEvent({
      channel: SSE_EVENT_CHANNELS.TASK_EVENTS,
      eventType: 'task_log',
      data: { task_id: '474', message: 'x' },
      id: undefined,
    })
    vi.advanceTimersByTime(400)

    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})
