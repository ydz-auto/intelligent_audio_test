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

/**
 * 构造「连接 OPEN 后 read() 持续挂起」的 SSE 响应：首帧立即吐出、之后等待
 * 外部 abort 信号，abort 时以 AbortError 终止挂起的 read——精确模拟浏览器中
 * fetch 的 AbortController.abort() 对响应体流的传播（mock fetch 不会自动接线，
 * 故由 wireAbort 手工把 init.signal 连到流的 error）。
 */
function hangingSseStream(): {
  response: Response
  wireAbort: (signal: AbortSignal) => void
} {
  let resolveAbort!: () => void
  const aborted = new Promise<void>((resolve) => {
    resolveAbort = resolve
  })
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        new TextEncoder().encode('event: task_log\ndata: {"msg":"a"}\n\n')
      )
      aborted.then(() => {
        controller.error(new DOMException('aborted', 'AbortError'))
      })
    },
  })
  return {
    response: sseResponse(stream),
    wireAbort: (signal) =>
      signal.addEventListener('abort', () => resolveAbort(), { once: true }),
  }
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

  it('连接 OPEN 且 read 挂起时 unsubscribe：立即终止、不再重连、无后续状态/事件回调（P1-1 回归）', async () => {
    vi.useFakeTimers()
    const { response, wireAbort } = hangingSseStream()
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.signal) wireAbort(init.signal)
      return Promise.resolve(response)
    })

    const events: string[] = []
    const statuses: string[] = []
    const off = subscribeSse({
      onEvent: (e) => events.push(e.eventType),
      onStatusChange: (s) => statuses.push(s),
    })
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(events).toEqual(['task_log'])
    expect(statuses).toContain('open')

    const statusesAtOff = statuses.length
    off()
    // 若 teardown 未置 stopped（P1-1 缺陷）：abort → read 抛 AbortError → catch
    // 排重连 → 退避窗口内必再次 fetch 且补发 reconnecting 状态；修复后两者皆不发生
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(events).toEqual(['task_log'])
    expect(statuses.slice(statusesAtOff)).toEqual([])
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
