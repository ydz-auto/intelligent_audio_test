/**
 * SSE 事件流订阅单测（接线基座 INT-605）。
 * 覆盖：SSE 帧解析、事件名→通道路由、通道过滤、同事件去重、
 * 断线指数退避重连、unsubscribe 终止、abort 终止。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '@/infrastructure/api/client'
import {
  subscribeSse,
  SSE_EVENT_CHANNELS,
} from '@/infrastructure/realtime/sse'

const fetchMock = vi.fn()

function streamFromText(text: string): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text))
      controller.close()
    },
  })
}

function sseResponse(stream: ReadableStream<Uint8Array>, status = 200): Response {
  return new Response(stream, {
    status,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('subscribeSse', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('解析 SSE 帧并按事件名路由到对应通道（TASK/REPORT）', async () => {
    const events: Array<{ channel: string | undefined; eventType: string; data: unknown }> = []
    const statuses: string[] = []
    fetchMock.mockResolvedValue(
      sseResponse(
        streamFromText(
          'event: task_progress\ndata: {"taskId":5,"progress":40}\n\n' +
            'event: report_generated\ndata: {"reportId":9}\n\n' +
            ': heartbeat\n\n'
        )
      )
    )

    const off = subscribeSse({
      onEvent: (e) => events.push(e),
      onStatusChange: (s) => statuses.push(s),
    })
    await flush()

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/sse/events`,
      expect.anything()
    )
    expect(statuses).toContain('open')
    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({
      channel: SSE_EVENT_CHANNELS.TASK_EVENTS,
      eventType: 'task_progress',
      data: { taskId: 5, progress: 40 },
    })
    expect(events[1]).toEqual({
      channel: SSE_EVENT_CHANNELS.REPORT_EVENTS,
      eventType: 'report_generated',
      data: { reportId: 9 },
    })
    off()
  })

  it('通道过滤：只投递所选通道事件', async () => {
    const events: Array<{ eventType: string; channel: string | undefined }> = []
    fetchMock.mockResolvedValue(
      sseResponse(
        streamFromText(
          'event: task_log\ndata: {"msg":"a"}\n\n' +
            'event: report_generated\ndata: {"reportId":1}\n\n'
        )
      )
    )

    const off = subscribeSse({
      channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS],
      onEvent: (e) => events.push(e),
    })
    await flush()

    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('report_generated')
    off()
  })

  it('同事件去重：窗口内相同 event+data 只投递一次', async () => {
    const events: Array<{ eventType: string }> = []
    fetchMock.mockResolvedValue(
      sseResponse(
        streamFromText(
          'event: task_progress\ndata: {"progress":10}\n\n' +
            'event: task_progress\ndata: {"progress":10}\n\n' +
            'event: task_progress\ndata: {"progress":20}\n\n'
        )
      )
    )

    const off = subscribeSse({ onEvent: (e) => events.push(e) })
    await flush()

    expect(events.map((e) => e.eventType)).toEqual([
      'task_progress',
      'task_progress',
    ])
    expect(events[0].eventType).toBe('task_progress')
    off()
  })

  it('断线后指数退避重连并继续投递', async () => {
    vi.useFakeTimers()
    fetchMock
      .mockResolvedValueOnce(sseResponse(streamFromText('')))
      .mockResolvedValueOnce(
        sseResponse(streamFromText('event: task_log\ndata: {"msg":"after"}\n\n'))
      )

    const events: Array<{ eventType: string; data: unknown }> = []
    const off = subscribeSse({
      onEvent: (e) => events.push(e),
      reconnectBaseMs: 100,
      reconnectMaxMs: 100,
    })

    // 第一次连接读到空流 → 立即结束 → 排定 100ms 重连
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(100)
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(0)

    expect(events).toHaveLength(1)
    expect(events[0].data).toEqual({ msg: 'after' })
    off()
  })

  it('unsubscribe 终止连接且不再重连', async () => {
    fetchMock.mockResolvedValue(sseResponse(streamFromText('')))
    const off = subscribeSse({ onEvent: () => undefined })
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    off()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('外部 signal.abort 终止连接且不再重连', async () => {
    const controller = new AbortController()
    fetchMock.mockResolvedValue(sseResponse(streamFromText('')))
    subscribeSse({ onEvent: () => undefined, signal: controller.signal })
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    controller.abort()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
