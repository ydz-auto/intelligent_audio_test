/**
 * Agent API 单测（INT-2457 §11 契约）：路径/幂等键/错误归一/SSE 续传终止。
 * fetch 全部 mock，不对应真实后端；端到端证据在 INT-2451+INT-2456 部署后补。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AGENT_ERROR_COPY, AGENT_RUN_STATUS } from '@/domain/models/agent'
import {
  AGENT_API_PATHS,
  cancelAgentRun,
  createAgentRun,
  subscribeAgentRunEvents,
  toAgentErrorMessage,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function sseResponse(text: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text))
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

async function waitUntil(check: () => boolean, timeoutMs = 5_000): Promise<void> {
  const start = Date.now()
  while (!check()) {
    if (Date.now() - start > timeoutMs) throw new Error('waitUntil 超时')
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
}

describe('agentApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('createAgentRun：POST /agent/sessions/{id}/runs + Idempotency-Key，响应转 camelCase', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ id: 'r-1', session_id: 's-1', status: 'RUNNING' })
      )
    vi.stubGlobal('fetch', fetchMock)

    const run = await createAgentRun('s-1', { message: '帮我生成报告' }, 'idem-1')

    expect(run).toMatchObject({
      id: 'r-1',
      sessionId: 's-1',
      status: AGENT_RUN_STATUS.RUNNING,
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`/api/v1${AGENT_API_PATHS.sessionRuns('s-1')}`)
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('idem-1')
    expect(JSON.parse(String(init.body))).toEqual({ message: '帮我生成报告' })
  })

  it('cancelAgentRun：空响应体返回 null（不因无 JSON 报错）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 200 }))
    )
    await expect(cancelAgentRun('r-1')).resolves.toBeNull()
  })

  it('错误归一：503=Agent 未开启、404=未部署、网络失败', () => {
    expect(toAgentErrorMessage(new ApiError({ httpStatus: 503 }))).toBe(
      AGENT_ERROR_COPY.disabled
    )
    expect(toAgentErrorMessage(new ApiError({ httpStatus: 404 }))).toBe(
      AGENT_ERROR_COPY.unavailable
    )
    expect(
      toAgentErrorMessage(
        new ApiError({ httpStatus: null, message: '', isNetworkError: true })
      )
    ).toBe(AGENT_ERROR_COPY.network)
    expect(toAgentErrorMessage(new ApiError({ httpStatus: 403 }))).toBe(
      AGENT_ERROR_COPY.unauthorized
    )
  })

  it('SSE：解析事件 → run_finished 终止；重连带 Last-Event-ID 与 cursor 续传', async () => {
    const fetchMock = vi
      .fn()
      // 第一次连接：吐一条 message_delta 后服务端关流 → 触发重连
      .mockResolvedValueOnce(
        sseResponse(
          'id: 1\nevent: message_delta\ndata: {"run_id":"r-1","sequence":1,"timestamp":"t","payload":{"message_id":"m-1","delta":"你好"}}\n\n'
        )
      )
      // 第二次连接：从游标续传终态
      .mockResolvedValueOnce(
        sseResponse(
          'id: 2\nevent: run_finished\ndata: {"run_id":"r-1","sequence":2,"timestamp":"t","payload":{"status":"SUCCEEDED"}}\n\n'
        )
      )
    vi.stubGlobal('fetch', fetchMock)

    const events: string[] = []
    const unsubscribe = subscribeAgentRunEvents('r-1', {
      onEvent: (event) => {
        events.push(
          event.type === 'message_delta' ? `${event.type}:${event.delta}` : event.type
        )
      },
    })

    await waitUntil(() => events.includes('run_finished'))
    unsubscribe()

    expect(events).toEqual(['message_delta:你好', 'run_finished'])
    expect(fetchMock).toHaveBeenCalledTimes(2)

    const secondInit = fetchMock.mock.calls[1][1] as RequestInit
    expect((secondInit.headers as Record<string, string>)['Last-Event-ID']).toBe('1')
    expect(String(fetchMock.mock.calls[1][0])).toContain('cursor=1')

    // 终态后不再重连
    await new Promise((resolve) => setTimeout(resolve, 1_200))
    expect(fetchMock).toHaveBeenCalledTimes(2)
  }, 15_000)

  it('SSE：503 不可恢复，直接失败且不重连', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 503 }))
    vi.stubGlobal('fetch', fetchMock)

    const failures: string[] = []
    const unsubscribe = subscribeAgentRunEvents('r-1', {
      onEvent: () => undefined,
      onFailure: (message) => failures.push(message),
    })

    await waitUntil(() => failures.length > 0)
    unsubscribe()
    expect(failures[0]).toBe(AGENT_ERROR_COPY.disabled)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('SSE：解绑后不再重连', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(''))
    vi.stubGlobal('fetch', fetchMock)

    const unsubscribe = subscribeAgentRunEvents('r-1', { onEvent: () => undefined })
    await waitUntil(() => fetchMock.mock.calls.length > 0)
    unsubscribe()
    await new Promise((resolve) => setTimeout(resolve, 1_200))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  }, 10_000)
})
