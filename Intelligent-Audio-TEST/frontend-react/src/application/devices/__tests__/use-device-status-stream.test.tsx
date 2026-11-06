/**
 * useDeviceStatusStream 单测：
 * - 无 sse:read 不建立订阅
 * - DEVICE_EVENTS 下同批 device_status_changed 合并为一次去抖失效（设备列表 + 开始测试资源）
 * - 非设备事件忽略
 */
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDeviceStatusStream } from '@/application/devices/use-device-status-stream'
import { DEVICE_STATUS_CHANGED_EVENT } from '@/domain/models/device'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { SSE_EVENT_CHANNELS, subscribeSse } from '@/infrastructure/realtime/sse'
import type { SseEvent } from '@/infrastructure/realtime/sse'

vi.mock('@/infrastructure/realtime/sse', () => ({
  SSE_EVENT_CHANNELS: {
    TASK_EVENTS: 'task_events',
    CASE_EVENTS: 'case_events',
    DEVICE_EVENTS: 'device_events',
    REPORT_EVENTS: 'report_events',
    CONFIG_EVENTS: 'config_events',
  },
  subscribeSse: vi.fn(),
}))

const subscribeMock = vi.mocked(subscribeSse)

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

function deviceEvent(deviceId: number): SseEvent {
  return {
    channel: SSE_EVENT_CHANNELS.DEVICE_EVENTS,
    eventType: DEVICE_STATUS_CHANGED_EVENT,
    data: { device_id: deviceId, status: 'offline' },
    id: undefined,
  }
}

describe('useDeviceStatusStream', () => {
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

    renderHook(() => useDeviceStatusStream(), { wrapper })

    expect(subscribeMock).not.toHaveBeenCalled()
  })

  it('订阅 DEVICE_EVENTS，同批事件去抖后只失效一次设备查询', () => {
    const { invalidateSpy, wrapper } = setup()
    renderHook(() => useDeviceStatusStream(), { wrapper })

    expect(subscribeMock).toHaveBeenCalledTimes(1)
    const options = subscribeMock.mock.calls[0][0] as {
      channels: string[]
      onEvent: (event: SseEvent) => void
    }
    expect(options.channels).toEqual([SSE_EVENT_CHANNELS.DEVICE_EVENTS])

    options.onEvent(deviceEvent(1))
    options.onEvent(deviceEvent(2))
    // 去抖窗口内不触发，避免一轮健康检查产生 N 次全量重拉
    expect(invalidateSpy).not.toHaveBeenCalled()

    vi.advanceTimersByTime(300)
    expect(invalidateSpy).toHaveBeenCalledTimes(2)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['devices'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['test-execution', 'devices'] })
  })

  it('非设备状态变更事件不触发失效', () => {
    const { invalidateSpy, wrapper } = setup()
    renderHook(() => useDeviceStatusStream(), { wrapper })

    const options = subscribeMock.mock.calls[0][0] as {
      onEvent: (event: SseEvent) => void
    }
    options.onEvent({
      channel: SSE_EVENT_CHANNELS.DEVICE_EVENTS,
      eventType: 'other_event',
      data: {},
      id: undefined,
    })
    vi.advanceTimersByTime(300)

    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})
