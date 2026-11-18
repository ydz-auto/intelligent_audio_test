/**
 * 输入区工具行（浮窗侧边会话）：对话记录 / 新建会话入口只在传入回调时渲染。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AiChatInputTools } from '../ai-chat-input-tools'

describe('AiChatInputTools 侧边会话入口', () => {
  it('传入回调时渲染对话记录 / 新建会话，点击各自触发回调', () => {
    const onToggleHistory = vi.fn()
    const onNewConversation = vi.fn()
    render(
      <AiChatInputTools
        onNewConversation={onNewConversation}
        onToggleHistory={onToggleHistory}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '对话记录' }))
    expect(onToggleHistory).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: '新建会话' }))
    expect(onNewConversation).toHaveBeenCalledTimes(1)
  })

  it('对话记录展开时 aria-pressed=true；未传入入口时不渲染', () => {
    const { rerender } = render(
      <AiChatInputTools historyOpen onToggleHistory={() => {}} />
    )
    expect(screen.getByRole('button', { name: '对话记录' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )

    rerender(<AiChatInputTools />)
    expect(screen.queryByRole('button', { name: '对话记录' })).toBeNull()
    expect(screen.queryByRole('button', { name: '新建会话' })).toBeNull()
  })

  it('生成中时新建会话禁用', () => {
    render(<AiChatInputTools disabled onNewConversation={() => {}} />)
    expect(screen.getByRole('button', { name: '新建会话' })).toBeDisabled()
  })
})
