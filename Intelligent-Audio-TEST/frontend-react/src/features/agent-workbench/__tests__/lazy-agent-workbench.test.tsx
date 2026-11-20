/**
 * Agent 工作台懒加载壳：浮窗关闭时不加载工作台本体分块；打开后才渲染。
 * 工作台本体以桩替代，只验证懒加载壳的开关门控（会话/浮窗行为由本体测试覆盖）。
 */
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LazyAgentWorkbench } from '@/features/agent-workbench/lazy-agent-workbench'
import { useAgentWorkbench } from '@/infrastructure/stores/agentWorkbenchStore'

vi.mock('@/features/agent-workbench/agent-workbench', () => ({
  AgentWorkbench: () => <div data-testid='agent-workbench-window' />,
}))

const initialStoreState = useAgentWorkbench.getState()

beforeEach(() => {
  useAgentWorkbench.setState({ open: false, minimized: false })
})

afterEach(() => {
  useAgentWorkbench.setState(initialStoreState)
})

describe('LazyAgentWorkbench 按需加载', () => {
  it('浮窗关闭时不渲染工作台', () => {
    render(<LazyAgentWorkbench />)

    expect(screen.queryByTestId('agent-workbench-window')).toBeNull()
  })

  it('浮窗打开后渲染工作台', async () => {
    useAgentWorkbench.setState({ open: true })

    render(<LazyAgentWorkbench />)

    expect(await screen.findByTestId('agent-workbench-window')).toBeTruthy()
  })
})
