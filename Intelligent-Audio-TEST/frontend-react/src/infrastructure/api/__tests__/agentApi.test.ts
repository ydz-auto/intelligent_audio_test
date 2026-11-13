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
  getAgentSession,
  listAgentApprovals,
  subscribeAgentRunEvents,
  toAgentErrorMessage,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'
import { AgentContractError } from '@/infrastructure/dto/agent.dto'

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

  it('createAgentRun：POST /agent/sessions/{id}/runs + Idempotency-Key，拆 {run, created} 信封', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          run: { id: 'r-1', session_id: 's-1', status: 'RUNNING' },
          created: true,
        },
        201
      )
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

  it('createAgentRun：幂等回放（created=false）同样取到 run', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ run: { id: 'r-9', session_id: 's-1', status: 'QUEUED' }, created: false })
      )
    )
    const run = await createAgentRun('s-1', { message: '重试' }, 'idem-1')
    expect(run.id).toBe('r-9')
    expect(run.status).toBe(AGENT_RUN_STATUS.QUEUED)
  })

  it('createAgentRun：扁平 run（旧草案）视为契约错误', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ id: 'r-2', session_id: 's-1', status: 'RUNNING' }))
    )
    await expect(createAgentRun('s-1', { message: '你好' }, 'idem-1')).rejects.toBeInstanceOf(
      AgentContractError
    )
  })

  it('getAgentSession：拆 {session, messages, runs} 信封', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          session: { id: 's-1', title: '会话' },
          messages: [{ role: 'user', content: '你好', tool_call_id: null }],
          runs: [{ id: 'r-1', session_id: 's-1', status: 'SUCCEEDED' }],
        })
      )
    )
    const detail = await getAgentSession('s-1')
    expect(detail.session.id).toBe('s-1')
    expect(detail.messages).toEqual([{ role: 'user', content: '你好', toolCallId: undefined }])
    expect(detail.runs[0]).toMatchObject({ id: 'r-1', status: AGENT_RUN_STATUS.SUCCEEDED })
  })

  it('listAgentApprovals：拆 {"items": [...]} 信封（M0 空列表）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ items: [] })))
    await expect(listAgentApprovals('r-1')).resolves.toEqual([])
  })

  it('listAgentApprovals：404 照常上抛（不伪装成空列表）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 404)))
    await expect(listAgentApprovals('r-1')).rejects.toBeInstanceOf(ApiError)
  })

  it('cancelAgentRun：按 RunResponse 解析快照', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ id: 'r-1', session_id: 's-1', status: 'CANCELLED' })
      )
    )
    await expect(cancelAgentRun('r-1')).resolves.toMatchObject({
      id: 'r-1',
      status: AGENT_RUN_STATUS.CANCELLED,
    })
  })

  it('cancelAgentRun：空响应体报错（不静默返回 null）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 200 }))
    )
    // 后端恒返 RunResponse；非 JSON 由 client 的响应体解析报错上抛
    await expect(cancelAgentRun('r-1')).rejects.toBeInstanceOf(Error)
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

  it('SSE：真实平铺帧 → run_finished 终止；重连带 Last-Event-ID 与 cursor 续传', async () => {
    const fetchMock = vi
      .fn()
      // 第一次连接：吐一条 message_delta 后服务端关流 → 触发重连
      .mockResolvedValueOnce(
        sseResponse(
          'id: 1\nevent: message_delta\ndata: {"message_id":"m-1","delta":"你好","index":0,"turn":1,"run_id":"r-1","sequence":1,"type":"message_delta","timestamp":"t"}\n\n'
        )
      )
      // 第二次连接：从游标续传终态
      .mockResolvedValueOnce(
        sseResponse(
          'id: 2\nevent: run_finished\ndata: {"status":"SUCCEEDED","reason":null,"error":null,"run_id":"r-1","sequence":2,"type":"run_finished","timestamp":"t"}\n\n'
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
