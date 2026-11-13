/**
 * Agent API 单测（INT-2457 §11 契约）：路径/幂等键/错误归一/SSE 续传终止。
 * fetch 全部 mock，不对应真实后端；端到端证据在 INT-2451+INT-2456 部署后补。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AGENT_ERROR_COPY,
  AGENT_RUN_STATUS,
  type AgentRunEvent,
} from '@/domain/models/agent'
import {
  AGENT_API_PATHS,
  cancelAgentRun,
  createAgentRun,
  decideAgentApproval,
  getAgentSession,
  listAgentApprovals,
  subscribeAgentRunEvents,
  toAgentErrorMessage,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'
import { AgentContractError } from '@/infrastructure/dto/agent.dto'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

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
    authTokenStore.clear()
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

  it('错误归一：503 按 code 区分「未开启 / 服务不可达」，404=会话或 run 不存在，网络失败', () => {
    // 网关总开关：FastAPI 把 HTTPException detail 落成 {"detail": {"code": "AGENT_DISABLED"}}
    expect(
      toAgentErrorMessage(
        new ApiError({
          httpStatus: 503,
          detail: { code: 'AGENT_DISABLED', message: 'Agent 未启用' },
        })
      )
    ).toBe(AGENT_ERROR_COPY.disabled)

    // agent_service 不可达时网关返回 {"detail": "agent service unavailable"}：
    // 是环境问题，不能报成「平台 Agent 当前未开启」
    expect(
      toAgentErrorMessage(
        new ApiError({ httpStatus: 503, detail: 'agent service unavailable' })
      )
    ).toBe(AGENT_ERROR_COPY.serviceUnavailable)
    // 凭据主密钥不可用等其他 503 同样按服务不可用处理
    expect(
      toAgentErrorMessage(
        new ApiError({
          httpStatus: 503,
          detail: 'credential store unavailable',
        })
      )
    ).toBe(AGENT_ERROR_COPY.serviceUnavailable)
    expect(toAgentErrorMessage(new ApiError({ httpStatus: 503 }))).toBe(
      AGENT_ERROR_COPY.serviceUnavailable
    )

    // 404 表示 run / session 不存在，不是「未部署」
    expect(toAgentErrorMessage(new ApiError({ httpStatus: 404 }))).toBe(
      AGENT_ERROR_COPY.notFound
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

  it('SSE：总开关关闭（503 + code=AGENT_DISABLED）报「未开启」，不重连', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ detail: { code: 'AGENT_DISABLED', message: 'Agent 未启用' } }, 503)
    )
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

  it('SSE：agent_service 不可达的 503 报「服务暂不可用」，不误报未开启', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: 'agent service unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    vi.stubGlobal('fetch', fetchMock)

    const failures: string[] = []
    const unsubscribe = subscribeAgentRunEvents('r-1', {
      onEvent: () => undefined,
      onFailure: (message) => failures.push(message),
    })

    await waitUntil(() => failures.length > 0)
    unsubscribe()
    expect(failures[0]).toBe(AGENT_ERROR_COPY.serviceUnavailable)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('SSE：401 先 refresh token 再重连，后续请求带新 token', async () => {
    authTokenStore.set('old-token')
    const fetchMock = vi
      .fn()
      // 首次订阅：token 过期
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      // refresh 换新 token
      .mockResolvedValueOnce(jsonResponse({ access_token: 'new-token' }))
      // 重连：续传终态
      .mockResolvedValueOnce(
        sseResponse(
          'id: 2\nevent: run_finished\ndata: {"status":"SUCCEEDED","run_id":"r-1","sequence":2,"type":"run_finished","timestamp":"t"}\n\n'
        )
      )
    vi.stubGlobal('fetch', fetchMock)

    const events: string[] = []
    const unsubscribe = subscribeAgentRunEvents('r-1', {
      onEvent: (event) => events.push(event.type),
    })

    await waitUntil(() => events.includes('run_finished'))
    unsubscribe()

    expect(fetchMock).toHaveBeenCalledTimes(3)
    const [refreshUrl, refreshInit] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(refreshUrl).toBe('/api/v1/auth/refresh')
    expect(refreshInit.method).toBe('POST')
    expect(authTokenStore.get()).toBe('new-token')

    const [eventsUrl, eventsInit] = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(String(eventsUrl)).toContain(AGENT_API_PATHS.runEvents('r-1'))
    expect((eventsInit.headers as Record<string, string>).Authorization).toBe(
      'Bearer new-token'
    )
    authTokenStore.clear()
  }, 15_000)

  it('SSE：网关合成的上游中断帧按可恢复事件下发，重连仍从水位续传', async () => {
    const fetchMock = vi
      .fn()
      // 上游中断：网关合成 error 帧，id 取已下发水位（3）
      .mockResolvedValueOnce(
        sseResponse(
          'id: 3\nevent: error\ndata: {"run_id":"r-1","sequence":3,"type":"error","timestamp":"t","code":"UPSTREAM_UNAVAILABLE","message":"上游事件流转发中断，请按 Last-Event-ID 续传"}\n\n'
        )
      )
      // 重连后从水位 3 续传终态
      .mockResolvedValueOnce(
        sseResponse(
          'id: 4\nevent: run_finished\ndata: {"status":"SUCCEEDED","run_id":"r-1","sequence":4,"type":"run_finished","timestamp":"t"}\n\n'
        )
      )
    vi.stubGlobal('fetch', fetchMock)

    const events: AgentRunEvent[] = []
    const unsubscribe = subscribeAgentRunEvents('r-1', {
      lastEventId: '3',
      onEvent: (event) => events.push(event),
    })

    await waitUntil(() => events.some((event) => event.type === 'run_finished'))
    unsubscribe()

    expect(events[0]).toMatchObject({
      type: 'error',
      errorCode: 'UPSTREAM_UNAVAILABLE',
      recoverable: true,
    })
    const secondInit = fetchMock.mock.calls[1][1] as RequestInit
    expect((secondInit.headers as Record<string, string>)['Last-Event-ID']).toBe('3')
    expect(String(fetchMock.mock.calls[1][0])).toContain('cursor=3')
  }, 15_000)

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

describe('agentApi 审批决策（INT-2472）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('decideAgentApproval：POST /agent/approvals/{id}/decision，body {decision}，解 {approval, run_status}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        approval: {
          id: 'ap-1',
          run_id: 'r-1',
          tool_call_id: 'tc-1',
          status: 'APPROVED',
          proposal: { tool: 'memory_write', risk: 'WRITE' },
          decided_by: 7,
          decided_at: '2026-11-14T02:03:00Z',
        },
        run_status: 'RUNNING',
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await decideAgentApproval('ap-1', 'APPROVE')

    expect(result.approval.status).toBe('APPROVED')
    expect(result.approval.decidedBy).toBe(7)
    expect(result.runStatus).toBe('RUNNING')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain(AGENT_API_PATHS.approvalDecision('ap-1'))
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ decision: 'APPROVE' })
  })

  it('decideAgentApproval：409（过期 / 并发）上抛 ApiError，由 store 刷新审批状态', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: '审批单已过期，写操作未执行', code: 'APPROVAL_EXPIRED' },
          409
        )
      )
    )
    await expect(decideAgentApproval('ap-1', 'APPROVE')).rejects.toMatchObject({
      httpStatus: 409,
    })
  })

  it('listAgentApprovals：真实列表项带 proposal / diff / decided_*，转 camelCase', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          items: [
            {
              id: 'ap-1',
              run_id: 'r-1',
              tool_call_id: 'tc-1',
              status: 'PENDING',
              proposal: { tool: 'memory_write', risk: 'WRITE', step_id: 'step-1' },
              diff: { kind: 'rest_request', method: 'POST', path: '/x' },
              expires_at: '2026-11-14T02:15:00Z',
            },
          ],
        })
      )
    )
    const items = await listAgentApprovals('r-1')
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      id: 'ap-1',
      status: 'PENDING',
      proposal: { tool: 'memory_write', risk: 'WRITE', stepId: 'step-1' },
      diff: { kind: 'rest_request', method: 'POST', path: '/x' },
      expiresAt: '2026-11-14T02:15:00Z',
    })
  })
})
