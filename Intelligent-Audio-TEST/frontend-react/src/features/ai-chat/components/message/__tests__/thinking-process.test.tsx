/**
 * 思考过程折叠（参照 Trae / Codex 的单行过程摘要）：
 * - 进行中自动展开，结束后收成一行「… · 调用 N 个工具」，点击才看逐条工具明细；
 * - 工具调用不再逐张铺整宽卡片（本用例保护折叠 / 展开的用户可见行为）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AgentToolCall } from '@/domain/models/aiChat'

import { ThinkingProcess } from '../thinking-process'

const TOOL_CALLS: AgentToolCall[] = [
  {
    id: 'tc-1',
    tool: 'report_query',
    label: 'report_query',
    status: 'completed',
    summary: '查询报告 420',
  },
  {
    id: 'tc-2',
    tool: 'task_query',
    label: 'task_query',
    status: 'completed',
    summary: '查询任务 407',
  },
]

describe('ThinkingProcess 过程折叠', () => {
  it('完成后收成一行摘要：显示工具次数，明细默认折叠', () => {
    render(<ThinkingProcess reasoning='' isReasoningStreaming={false} durationSeconds={0} toolCalls={TOOL_CALLS} />)

    expect(screen.getByRole('button', { name: /调用 2 个工具/ })).toBeInTheDocument()
    expect(screen.queryByText('report_query')).not.toBeInTheDocument()
  })

  it('点开摘要：逐条工具明细与摘要可见', async () => {
    const user = userEvent.setup()
    render(<ThinkingProcess reasoning='' isReasoningStreaming={false} durationSeconds={0} toolCalls={TOOL_CALLS} />)

    await user.click(screen.getByRole('button', { name: /调用 2 个工具/ }))

    expect(screen.getByText('report_query')).toBeVisible()
    expect(screen.getByText('task_query')).toBeVisible()
  })

  it('工具执行中自动展开：过程未结束时不把明细藏起来', () => {
    render(
      <ThinkingProcess
        reasoning=''
        isReasoningStreaming={false}
        durationSeconds={0}
        toolCalls={[{ ...TOOL_CALLS[0], status: 'running' }]}
      />
    )

    expect(screen.getByText('report_query')).toBeVisible()
    expect(screen.getByText('正在思考')).toBeInTheDocument()
  })

  it('从执行中转为完成：摘要行改为耗时口径并自动收起明细', () => {
    const { rerender } = render(
      <ThinkingProcess
        reasoning='先核对报告'
        isReasoningStreaming
        durationSeconds={0}
        toolCalls={[{ ...TOOL_CALLS[0], status: 'running' }]}
      />
    )
    expect(screen.getByText('report_query')).toBeVisible()

    rerender(
      <ThinkingProcess
        reasoning='先核对报告'
        isReasoningStreaming={false}
        durationSeconds={6}
        toolCalls={[{ ...TOOL_CALLS[0], status: 'completed' }]}
      />
    )

    expect(screen.getByRole('button', { name: /思考了 6 秒/ })).toBeInTheDocument()
    expect(screen.queryByText('report_query')).not.toBeInTheDocument()
  })
})
