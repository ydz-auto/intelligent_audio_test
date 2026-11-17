/**
 * 工具执行卡错误码展示：成功结果的状态码（后端常见 'OK'）不是错误，
 * 不能渲染成红色「错误码」；只有失败结果才展示错误码。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AgentToolCall } from '@/domain/models/aiChat'
import { ToolCallCard } from '../tool-call-card'

const BASE: AgentToolCall = {
  id: 'tc-1',
  tool: 'platform_contract',
  label: 'platform_contract',
  status: 'completed',
  summary: '{"query":"报告导出 权限码","section":"all"}',
}

describe('ToolCallCard 错误码', () => {
  it('已完成带状态码 OK：不展示「错误码」', () => {
    render(<ToolCallCard call={{ ...BASE, errorCode: 'OK' }} />)
    expect(screen.queryByText(/错误码/)).not.toBeInTheDocument()
  })

  it('失败结果：展开后展示错误码', async () => {
    const user = userEvent.setup()
    render(
      <ToolCallCard
        call={{ ...BASE, status: 'error', errorCode: 'TOOL_EXECUTION_ERROR' }}
      />
    )
    await user.click(screen.getByRole('button', { name: /platform_contract/ }))
    expect(
      screen.getByText('错误码：TOOL_EXECUTION_ERROR')
    ).toBeInTheDocument()
  })
})
