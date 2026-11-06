/**
 * waitForReportGenerated 单测（INT-935 异步生成 SSE 等待）。
 * mock infrastructure/realtime/sse 的 subscribeSse，直接驱动 onEvent 断言
 * 匹配/失败/超时/取消四类路径。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const sseState = vi.hoisted(() => {
  const handlers: Array<(event: { eventType: string; data: unknown }) => void> = []
  const unsubscribe = vi.fn(() => undefined)
  return {
    handlers,
    unsubscribe,
    subscribeSse: vi.fn((options: { onEvent: (event: { eventType: string; data: unknown }) => void }) => {
      handlers.push(options.onEvent)
      return unsubscribe
    }),
  }
})

const { unsubscribe } = sseState

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

import { waitForReportGenerated } from '@/application/reports/use-report-compare'

function emit(eventType: string, data: unknown): void {
  for (const handler of sseState.handlers) {
    handler({ eventType, data })
  }
}

describe('waitForReportGenerated', () => {
  beforeEach(() => {
    sseState.handlers.length = 0
    sseState.subscribeSse.mockClear()
    unsubscribe.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reportKey：secondary_compare_generated 按 reportIds 升序匹配后 resolve reportId', async () => {
    const promise = waitForReportGenerated({ reportKey: [65, 2] })
    emit('secondary_compare_generated', {
      reportIds: [2, 65],
      reportId: 99,
      success: true,
      status: 'completed',
    })
    await expect(promise).resolves.toBe(99)
    expect(unsubscribe).toHaveBeenCalled()
  })

  it('taskId：report_generated 按 taskId 匹配后 resolve reportId', async () => {
    const promise = waitForReportGenerated({ taskId: 1042 })
    emit('report_generated', {
      taskId: 1042,
      reportId: 120,
      success: true,
      status: 'completed',
    })
    await expect(promise).resolves.toBe(120)
    expect(unsubscribe).toHaveBeenCalled()
  })

  it('不匹配的 reportIds 事件被忽略，匹配事件到达后才 resolve', async () => {
    const promise = waitForReportGenerated({ reportKey: [2, 65] })
    emit('secondary_compare_generated', {
      reportIds: [3, 4],
      reportId: 999,
      success: true,
    })
    emit('secondary_compare_generated', {
      reportIds: [65, 2],
      reportId: 88,
      success: true,
    })
    await expect(promise).resolves.toBe(88)
  })

  it('失败事件（success=false）reject 错误信息', async () => {
    const promise = waitForReportGenerated({ reportKey: [2, 65] })
    emit('secondary_compare_generated', {
      reportIds: [2, 65],
      success: false,
      error: '对比报告生成失败，请稍后重试',
    })
    await expect(promise).rejects.toThrow('对比报告生成失败，请稍后重试')
    expect(unsubscribe).toHaveBeenCalled()
  })

  it('signal.abort 取消等待并解绑 SSE', async () => {
    const controller = new AbortController()
    const promise = waitForReportGenerated({ taskId: 1042 }, { signal: controller.signal })
    controller.abort()
    await expect(promise).rejects.toThrow('已取消')
    expect(unsubscribe).toHaveBeenCalled()
  })

  it('超时 reject 并解绑 SSE', async () => {
    vi.useFakeTimers()
    const promise = waitForReportGenerated({ taskId: 1042 }, { timeoutMs: 1_000 })
    vi.advanceTimersByTime(1_000)
    await expect(promise).rejects.toThrow('报告生成超时，请稍后重试')
    expect(unsubscribe).toHaveBeenCalled()
  })
})
