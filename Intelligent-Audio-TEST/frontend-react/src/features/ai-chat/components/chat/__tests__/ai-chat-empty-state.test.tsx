/**
 * AI 对话组件测试——AiChatEmptyState（INT-435）：空态标题/描述渲染、
 * starter 按权限过滤、点击回填输入框（不自动发送，对位 08_AI对话页.md §3.3）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AiChatEmptyState } from '@/features/ai-chat/components/chat/ai-chat-empty-state'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

const initialAuth = useAuthStore.getState()

beforeEach(() => {
  useAuthStore.getState().setAuth(null)
})

afterEach(() => {
  useAuthStore.setState(initialAuth)
})

describe('AiChatEmptyState', () => {
  it('渲染标题与描述', () => {
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(screen.getByText('开始与 AI 助手对话')).toBeInTheDocument()
    expect(screen.getByText(/AI 基于报告数据起草文档/)).toBeInTheDocument()
  })

  it('未登录权限全失：starter 不渲染', () => {
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(
      screen.queryByRole('button', { name: /生成测试报告/ })
    ).not.toBeInTheDocument()
  })

  it('超级管理员可见全部四枚 starter', () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(
      screen.getByRole('button', { name: /生成测试报告/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /对比多份报告/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /解读报告指标/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /追问报告数据/ })
    ).toBeInTheDocument()
  })

  it('仅 report:read 时可见解读/追问，隐藏生成与对比', () => {
    useAuthStore.getState().setAuth({
      id: 'u2',
      username: 'reader',
      displayName: '报告读者',
      roleName: '访客',
      permissions: ['report:read'],
    })
    render(<AiChatEmptyState onFillPrompt={vi.fn()} />)
    expect(
      screen.queryByRole('button', { name: /生成测试报告/ })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /对比多份报告/ })
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /解读报告指标/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /追问报告数据/ })
    ).toBeInTheDocument()
  })

  it('点击 starter 回填提示词', async () => {
    useAuthStore.getState().setAuth({
      id: 'u1',
      username: 'demo_admin',
      displayName: '演示管理员',
      roleName: '超级管理员',
      permissions: ['*'],
    })
    const user = userEvent.setup()
    const onFillPrompt = vi.fn()
    render(<AiChatEmptyState onFillPrompt={onFillPrompt} />)
    await user.click(
      screen.getByRole('button', { name: /生成测试报告/ })
    )
    expect(onFillPrompt).toHaveBeenCalledWith(
      '帮我把最近的测试任务生成一份测试报告'
    )
  })
})
