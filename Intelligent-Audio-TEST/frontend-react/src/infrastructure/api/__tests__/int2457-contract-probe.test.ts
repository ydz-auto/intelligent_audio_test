/**
 * INT-2457 契约回归探针（测试工程师 2026-11-12 提供，返工后作为本卡契约用例保留）。
 * 数据来源：INT-2451 交付 69fa26cc0
 *  - api_gateway/routes/agent_runtime_bp.py：透明转发（iter_raw），不拆信封
 *  - agent_service/interfaces/api/schemas.py：CreateRunResponse{run, created}
 *  - agent_service/interfaces/api/routes.py::_sse_frame：event.payload 字段平铺进 data
 *  - agent_service/application/run_orchestrator.py：tool_result 载荷键 ok/content/error_code
 *
 * 修复前 4/4 失败；修复后应全绿。新增字段/事件时不得修改本文件的期望形态。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AGENT_TOOL_RESULT_STATUS,
  AGENT_RUN_STATUS,
} from '@/domain/models/agent'
import type { AgentRunEvent } from '@/domain/models/agent'
import {
  createAgentRun,
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

describe('INT-2457 契约探针（真实后端形态）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('POST /runs 真实响应 {run, created} → 必须能取到 run.id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            run: {
              id: 'r-1',
              session_id: 's-1',
              owner_id: 1,
              tenant_id: 'default',
              status: 'QUEUED',
              model: 'm',
              budget: {},
              token_in: 0,
              token_out: 0,
              error: null,
              created_at: 't',
              started_at: null,
              finished_at: null,
            },
            created: true,
          },
          201
        )
      )
    )
    const run = await createAgentRun('s-1', { message: '你好' }, 'idem-1')
    expect(run.id).toBe('r-1')
    expect(run.sessionId).toBe('s-1')
    expect(run.status).toBe(AGENT_RUN_STATUS.QUEUED)
  })

  it('SSE 平铺载荷的 message_delta → 必须产出事件', async () => {
    const events = await collect(
      'id: 1\nevent: message_delta\ndata: {"message_id":"m-1","delta":"你好","index":0,"turn":1,"run_id":"r-1","sequence":1,"type":"message_delta","timestamp":"t"}\n\n'
    )
    expect(events.map((e) => e.type)).toEqual(['message_delta'])
  })

  it('SSE 平铺载荷的 run_finished(CANCELLED) → 必须保留 CANCELLED', async () => {
    const events = await collect(
      'id: 2\nevent: run_finished\ndata: {"status":"CANCELLED","reason":"user_cancelled","error":null,"run_id":"r-1","sequence":2,"type":"run_finished","timestamp":"t"}\n\n'
    )
    expect(events).toHaveLength(1)
    const finished = events[0]
    expect(
      finished.type === 'run_finished' ? finished.status : undefined
    ).toBe(AGENT_RUN_STATUS.CANCELLED)
  })

  it('SSE 平铺载荷的 tool_result(ok=false) → 必须标 FAILED', async () => {
    const events = await collect(
      'id: 3\nevent: tool_result\ndata: {"tool_call_id":"tc-1","tool":"query","ok":false,"content":"boom","error_code":"E1","turn":1,"run_id":"r-1","sequence":3,"type":"tool_result","timestamp":"t"}\n\n'
    )
    expect(events).toHaveLength(1)
    const result = events[0]
    expect(
      result.type === 'tool_result' ? result.status : undefined
    ).toBe(AGENT_TOOL_RESULT_STATUS.FAILED)
  })
})
