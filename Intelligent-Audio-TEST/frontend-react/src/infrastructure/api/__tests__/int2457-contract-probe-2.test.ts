/**
 * INT-2457 补充契约探针（测试工程师 2026-11-12 复测）。
 * 覆盖首轮打回清单里的 P1-1（tool_call 摘要取 arguments）与 P2（approvals 信封 /
 * session 详情信封 / run_started 无 status），以及 run_finished / tool_result 的
 * 非平凡终态。数据形态全部取自 agent_service 真实实现：
 *  - routes.py::_sse_frame：事件字段平铺在 data 顶层
 *  - schemas.py：CreateRunResponse{run, created} / SessionDetailResponse{session, messages, runs}
 *  - routes.py::list_approvals：{"items": [...]}
 *  - run_orchestrator.py：tool_call{arguments, risk} / tool_result{ok, content, error_code}
 *  - run_orchestrator.py::_finish：run_finished{status, reason, error}
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AGENT_RUN_STATUS,
  AGENT_TOOL_RESULT_STATUS,
} from '@/domain/models/agent'
import type { AgentRunEvent } from '@/domain/models/agent'
import {
  getAgentSession,
  listAgentApprovals,
  subscribeAgentRunEvents,
} from '@/infrastructure/api/agentApi'

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

async function collect(text: string): Promise<AgentRunEvent[]> {
  const events: AgentRunEvent[] = []
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(text)))
  const unsubscribe = subscribeAgentRunEvents('r-1', {
    onEvent: (event) => events.push(event),
    onFailure: () => undefined,
  })
  await new Promise((resolve) => setTimeout(resolve, 600))
  unsubscribe()
  return events
}

describe('INT-2457 补充契约探针（真实后端形态）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('GET /sessions/{id} 信封 {session, messages, runs} 必须拆开', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          session: {
            id: 's-1',
            owner_id: 1,
            tenant_id: 'default',
            title: '会话',
            active_skill: null,
            model: 'm',
            created_at: 't',
            updated_at: 't',
          },
          messages: [
            { role: 'user', content: '你好', tool_call_id: null },
            { role: 'assistant', content: '在', tool_call_id: 'tc-1' },
          ],
          runs: [
            {
              id: 'r-1',
              session_id: 's-1',
              status: 'SUCCEEDED',
              model: 'm',
              budget: {},
              token_in: 1,
              token_out: 2,
              error: null,
            },
          ],
        })
      )
    )
    const detail = await getAgentSession('s-1')
    expect(detail.session.id).toBe('s-1')
    expect(detail.session.title).toBe('会话')
    expect(detail.messages).toHaveLength(2)
    expect(detail.messages[1].toolCallId).toBe('tc-1')
    expect(detail.runs[0].id).toBe('r-1')
    expect(detail.runs[0].status).toBe(AGENT_RUN_STATUS.SUCCEEDED)
  })

  it('GET /runs/{id}/approvals {"items": [...]} 必须解出列表', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          items: [
            {
              id: 'a-1',
              run_id: 'r-1',
              tool_call_id: 'tc-1',
              status: 'PENDING',
              proposal: { tool: 'write_x' },
            },
          ],
        })
      )
    )
    const approvals = await listAgentApprovals('r-1')
    expect(approvals).toHaveLength(1)
    expect(approvals[0].id).toBe('a-1')
    expect(approvals[0].status).toBe('PENDING')
  })

  it('approvals 空信封 {"items": []} → 空数组', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ items: [] }))
    )
    await expect(listAgentApprovals('r-1')).resolves.toEqual([])
  })

  it('tool_call 平铺 arguments → 摘要取 arguments、risk 保留', async () => {
    const events = await collect(
      'id: 1\nevent: tool_call\ndata: {"tool_call_id":"tc-1","tool":"dashboard_query","arguments":{"metric":"latency","limit":5},"risk":"READ","turn":1,"run_id":"r-1","sequence":1,"type":"tool_call","timestamp":"t"}\n\n'
    )
    expect(events).toHaveLength(1)
    const call = events[0]
    if (call.type !== 'tool_call') throw new Error('expected tool_call')
    expect(call.toolCallId).toBe('tc-1')
    expect(call.risk).toBe('READ')
    expect(call.summary).toContain('latency')
  })

  it('tool_call 无 arguments/无 summary → 不抛错且摘要为空', async () => {
    const events = await collect(
      'id: 1\nevent: tool_call\ndata: {"tool_call_id":"tc-2","tool":"noop","arguments":{},"risk":"READ","turn":1,"run_id":"r-1","sequence":1,"type":"tool_call","timestamp":"t"}\n\n'
    )
    expect(events).toHaveLength(1)
    const call = events[0]
    if (call.type !== 'tool_call') throw new Error('expected tool_call')
    expect(call.summary).toBeUndefined()
  })

  it('tool_result ok=true → SUCCEEDED 且摘要取 content', async () => {
    const events = await collect(
      'id: 2\nevent: tool_result\ndata: {"tool_call_id":"tc-1","tool":"q","ok":true,"content":"结果正文","error_code":null,"turn":1,"run_id":"r-1","sequence":2,"type":"tool_result","timestamp":"t"}\n\n'
    )
    expect(events).toHaveLength(1)
    const result = events[0]
    if (result.type !== 'tool_result') throw new Error('expected tool_result')
    expect(result.status).toBe(AGENT_TOOL_RESULT_STATUS.SUCCEEDED)
    expect(result.summary).toBe('结果正文')
  })

  it('run_finished BUDGET_EXCEEDED 必须原样保留（不得归一为成功）', async () => {
    const events = await collect(
      'id: 3\nevent: run_finished\ndata: {"status":"BUDGET_EXCEEDED","reason":"max_tokens","error":null,"run_id":"r-1","sequence":3,"type":"run_finished","timestamp":"t"}\n\n'
    )
    expect(events).toHaveLength(1)
    const finished = events[0]
    if (finished.type !== 'run_finished') throw new Error('expected run_finished')
    expect(finished.status).toBe(AGENT_RUN_STATUS.BUDGET_EXCEEDED)
  })

  it('run_finished 缺 status 但有 error → FAILED', async () => {
    const events = await collect(
      'id: 4\nevent: run_finished\ndata: {"reason":"crash","error":"模型超时","run_id":"r-1","sequence":4,"type":"run_finished","timestamp":"t"}\n\n'
    )
    expect(events).toHaveLength(1)
    const finished = events[0]
    if (finished.type !== 'run_finished') throw new Error('expected run_finished')
    expect(finished.status).toBe(AGENT_RUN_STATUS.FAILED)
    expect(finished.error).toBe('模型超时')
  })

  it('keep-alive 注释帧不产生事件，正常帧照常解析', async () => {
    const events = await collect(
      ': keep-alive\n\nid: 5\nevent: message_delta\ndata: {"message_id":"m-1","delta":"好","index":0,"turn":1,"run_id":"r-1","sequence":5,"type":"message_delta","timestamp":"t"}\n\n'
    )
    expect(events.map((e) => e.type)).toEqual(['message_delta'])
  })
})
