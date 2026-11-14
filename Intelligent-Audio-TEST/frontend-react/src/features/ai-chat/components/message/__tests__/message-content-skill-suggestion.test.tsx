/**
 * 消息编排层「建议卡 → store」接线（INT-2584）：
 * 点「忽略」后共享消息列表里该条消息的建议被清掉（卡片随之卸载、正文不动），
 * 不产生任何请求；这层接线是忽略语义的唯一写点。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '@/domain/models/aiChat'
import { AiChatMessageContent } from '@/features/ai-chat/components/message/message-content'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'

// 卡片里的「去创建草稿」是 TanStack Link：测试不挂 RouterProvider，降级为 <a>
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, ...props }: React.ComponentProps<'a'>) => (
      <a {...props}>{children}</a>
    ),
  }
})

const message: ChatMessage = {
  key: 'assistant-1',
  from: 'assistant',
  versions: [{ id: 'assistant-1-v1', content: '已整理本次导出流程。' }],
  status: 'complete',
  skillSuggestion: {
    suggestedName: 'platform-contract-tool-search',
    description: '基于本次 run 的执行流程沉淀的 Skill 草案',
    toolsUsed: ['platform_contract', 'tool_search'],
    created: false,
    requiresConfirmation: true,
  },
}

/** 按共享 store 渲染：忽略写回 store 后宿主重新渲染（与页面真实链路同构） */
function Host() {
  const messages = useAiChatSession((state) => state.messages)
  const current = messages.find((item) => item.key === message.key) ?? messages[0]
  if (!current) return null
  return (
    <AiChatMessageContent
      alignment='left'
      message={current}
      versionContent={current.versions[0]?.content ?? ''}
    />
  )
}

describe('AiChatMessageContent 建议卡忽略接线', () => {
  it('点「忽略」：卡片消失、正文与其他内容不动、Network 无请求、store 建议被清', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    useAiChatSession.setState({ messages: [message] })

    render(<Host />)
    expect(screen.getByTestId('skill-suggestion-card')).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('skill-suggestion-dismiss'))

    await waitFor(() => {
      expect(screen.queryByTestId('skill-suggestion-card')).not.toBeInTheDocument()
    })
    expect(screen.getByText('已整理本次导出流程。')).toBeInTheDocument()
    expect(
      useAiChatSession.getState().messages[0]?.skillSuggestion
    ).toBeUndefined()
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })
})
