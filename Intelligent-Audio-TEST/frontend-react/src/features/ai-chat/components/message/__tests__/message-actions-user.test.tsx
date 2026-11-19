/**
 * 用户消息操作组：用户输入必须可复制 / 编辑 / 删除。
 *
 * 回归背景：user 气泡此前在 AiChatMessageContent 里直接 return 纯文本，操作组
 * 从未渲染，导致「用户的输入没法删除」；同时 MessageActions 的源码按钮只判
 * hasContent，未挂 onToggleSource 时也会渲染成点不动的死按钮。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '@/domain/models/aiChat'
import { AiChatMessageContent } from '@/features/ai-chat/components/message/message-content'
import { MessageActions } from '@/features/ai-chat/components/message/message-actions'
import { MESSAGE_STATUS } from '@/features/ai-chat/constants'

function makeUserMessage(): ChatMessage {
  return {
    key: 'user-1',
    from: 'user',
    versions: [{ id: 'user-1-v1', content: '用户的输入' }],
    status: MESSAGE_STATUS.COMPLETE,
    createdAt: Date.now(),
  }
}

describe('用户消息操作组', () => {
  it('user 气泡渲染操作组（删除入口可用）', () => {
    render(
      <AiChatMessageContent
        actions={<button type='button'>删除</button>}
        alignment='right'
        message={makeUserMessage()}
        versionContent='用户的输入'
      />
    )

    expect(screen.getByText('用户的输入')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
  })

  it('未挂源码 / 重新生成处理器时不渲染对应按钮（避免死按钮）', () => {
    render(
      <MessageActions
        message={makeUserMessage()}
        onDelete={vi.fn()}
        onEdit={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '编辑' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '显示源码' })).toBeNull()
    expect(screen.queryByRole('button', { name: '重新生成' })).toBeNull()
  })
})
