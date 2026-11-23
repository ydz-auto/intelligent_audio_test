/**
 * sse-bus（共享单连接总线）单测：
 * - 多订阅者只建立一条底层 SSE 连接（引用计数生命周期）
 * - 事件按订阅者声明的 channel 子集分发；未知通道事件全量透传
 * - 最后一个订阅者解绑才断开共享连接
 * - 新订阅者立即回放当前连接状态（open 不重等 connecting）
 * - signal abort 解绑订阅者并触发引用计数归零
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { subscribeSharedSse } from '@/infrastructure/realtime/sse-bus'
import { SSE_EVENT_CHANNELS, subscribeSse } from '@/infrastructure/realtime/sse'
import type { SseEvent, SseStatus } from '@/infrastructure/realtime/sse'

const sseState = vi.hoisted(() => {
  let options: {
    onEvent: (event: SseEvent) => void
    onStatusChange?: (status: SseStatus) => void
  } | null = null
  const teardown = vi.fn(() => undefined)
  const subscribeSse = vi.fn((opts: {
    onEvent: (event: SseEvent) => void
    onStatusChange?: (status: SseStatus) => void
  }) => {
    options = opts
    return teardown
  })
  const emit = (event: SseEvent): void => {
    options?.onEvent(event)
  }
  const emitStatus = (status: SseStatus): void => {
    options?.onStatusChange?.(status)
  }
  return { subscribeSse, teardown, emit, emitStatus }
})

vi.mock('@/infrastructure/realtime/sse', () => ({
  SSE_EVENT_CHANNELS: {
    TASK_EVENTS: 'task_events',
    CASE_EVENTS: 'case_events',
    DEVICE_EVENTS: 'device_events',
    REPORT_EVENTS: 'report_events',
    CONFIG_EVENTS: 'config_events',
  },
  subscribeSse: sseState.subscribeSse,
}))

const subscribeMock = vi.mocked(subscribeSse)

function reportEvent(eventType = 'report_generated'): SseEvent {
  return {
    channel: SSE_EVENT_CHANNELS.REPORT_EVENTS,
    eventType,
    data: {},
    id: undefined,
  }
}

describe('subscribeSharedSse', () => {
  beforeEach(() => {
    subscribeMock.mockClear()
    sseState.teardown.mockClear()
  })

  it('多个订阅者共享同一条底层 SSE 连接，最后一个解绑才断开', () => {
    const offA = subscribeSharedSse({ channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS], onEvent: vi.fn() })
    const offB = subscribeSharedSse({ channels: [SSE_EVENT_CHANNELS.DEVICE_EVENTS], onEvent: vi.fn() })

    expect(subscribeMock).toHaveBeenCalledTimes(1)

    // 部分解绑：连接保持
    offA()
    expect(sseState.teardown).not.toHaveBeenCalled()

    // 全部解绑：断开共享连接
    offB()
    expect(sseState.teardown).toHaveBeenCalledTimes(1)

    // 重新订阅：建立新连接
    const offC = subscribeSharedSse({ onEvent: vi.fn() })
    expect(subscribeMock).toHaveBeenCalledTimes(2)
    offC()
  })

  it('事件按订阅者声明的 channel 子集分发，未知通道事件全量透传', () => {
    const reportHandler = vi.fn()
    const deviceHandler = vi.fn()
    const allHandler = vi.fn()
    const offReport = subscribeSharedSse({
      channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS],
      onEvent: reportHandler,
    })
    const offDevice = subscribeSharedSse({
      channels: [SSE_EVENT_CHANNELS.DEVICE_EVENTS],
      onEvent: deviceHandler,
    })
    const offAll = subscribeSharedSse({ onEvent: allHandler })

    sseState.emit(reportEvent())
    expect(reportHandler).toHaveBeenCalledTimes(1)
    expect(deviceHandler).not.toHaveBeenCalled()
    expect(allHandler).toHaveBeenCalledTimes(1)

    sseState.emit({
      channel: SSE_EVENT_CHANNELS.DEVICE_EVENTS,
      eventType: 'device_status_changed',
      data: {},
      id: undefined,
    })
    expect(reportHandler).toHaveBeenCalledTimes(1)
    expect(deviceHandler).toHaveBeenCalledTimes(1)

    // channel 未知：透传给全部订阅者（既有 subscribeSse 语义）；
    // allHandler 无过滤，三条事件全收
    sseState.emit({
      channel: undefined,
      eventType: 'unknown_event',
      data: {},
      id: undefined,
    })
    expect(reportHandler).toHaveBeenCalledTimes(2)
    expect(deviceHandler).toHaveBeenCalledTimes(2)
    expect(allHandler).toHaveBeenCalledTimes(3)

    offReport()
    offDevice()
    offAll()
  })

  it('新订阅者立即回放当前连接状态，open 时无需重等 connecting', () => {
    const statusFirst = vi.fn()
    const offFirst = subscribeSharedSse({
      channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS],
      onEvent: vi.fn(),
      onStatusChange: statusFirst,
    })
    // 模拟底层连接建立成功
    sseState.emitStatus('open')

    const statusLate = vi.fn()
    const offLate = subscribeSharedSse({ onEvent: vi.fn(), onStatusChange: statusLate })
    expect(statusLate).toHaveBeenLastCalledWith('open')

    offFirst()
    offLate()
  })

  it('signal 终止时仅解绑该订阅者，其余订阅者仍持有连接', () => {
    const controller = new AbortController()
    const offA = subscribeSharedSse({ onEvent: vi.fn(), signal: controller.signal })
    const offB = subscribeSharedSse({ onEvent: vi.fn() })

    controller.abort()
    expect(sseState.teardown).not.toHaveBeenCalled()

    // abort 后主动解绑幂等：不重复断开
    offA()
    expect(sseState.teardown).not.toHaveBeenCalled()

    offB()
    expect(sseState.teardown).toHaveBeenCalledTimes(1)
  })

  it('同一事件分发到所有匹配订阅者，各订阅者各收一次', () => {
    const h1 = vi.fn()
    const h2 = vi.fn()
    const off1 = subscribeSharedSse({ channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS], onEvent: h1 })
    const off2 = subscribeSharedSse({ channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS], onEvent: h2 })

    sseState.emit(reportEvent())
    expect(h1).toHaveBeenCalledTimes(1)
    expect(h2).toHaveBeenCalledTimes(1)

    off1()
    off2()
  })
})
