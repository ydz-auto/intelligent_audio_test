/**
 * use-chat-state 单测（INT-598 代码审计返修 P2-2/P2-3）：
 * - URL 契约预填：/ai-chat?report={id} / /ai-chat?task={id} 进入即预填指令（§3.7）；
 * - 两形态同 store：整页与全局浮窗共用 infrastructure/stores/aiChatSessionStore 单一会话
 *   实例，一实例更新、另一实例可见（§3.1B「不分裂会话」），并 500ms 防抖持久化。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useChatState } from '@/features/ai-chat/hooks/use-chat-state'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'
import { aiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'
import type { ChatMessage } from '@/domain/models/aiChat'

function makeUserMessage(content: string): ChatMessage {
  return {
    key: `user-${content}`,
    from: 'user',
    versions: [{ id: `user-${content}-v1`, content }],
    createdAt: Date.now(),
  }
}

describe('useChatState（URL 契约预填 + 两形态同 store）', () => {
  beforeEach(() => {
    // 复位共享 store（config/messages/appliedContextKey），避免跨用例污染；
    // 再清 localStorage（store 订阅会持久化复位后的 config，须在其后清掉，
    // 保证 URL 契约用例以「无存档」状态验证 report/task 上下文绑定）。
    useAiChatSession.setState({
      config: { providerId: undefined, modelId: undefined },
      messages: [],
      appliedContextKey: undefined,
    })
    window.localStorage.clear()
  })

  it('report URL 进入即预填「帮我把报告 #{id} 的测试结果生成一份可交付报告」（§3.7）', () => {
    const { result } = renderHook(() => useChatState({ report: '320' }))
    expect(result.current.initialPrompt).toBe(
      '帮我把报告 #320 的测试结果生成一份可交付报告'
    )
    // 报告在 MOCK_REPORTS 在册：config 绑定报告上下文
    expect(result.current.config.reportContextId).toBe('320')
    expect(result.current.config.reportContextLabel).toContain('T320')
  })

  it('task URL 进入即预填「帮我把任务 #{id} 的测试结果生成一份报告」（§3.7）', () => {
    const { result } = renderHook(() => useChatState({ task: '320' }))
    expect(result.current.initialPrompt).toBe(
      '帮我把任务 #320 的测试结果生成一份报告'
    )
    expect(result.current.config.reportContextId).toBe('320')
    expect(result.current.config.reportContextType).toBe('task_context')
  })

  it('无 URL 上下文：不预填、走空态（§3.7 侧栏裸入口）', () => {
    const { result } = renderHook(() => useChatState())
    expect(result.current.initialPrompt).toBeUndefined()
    expect(result.current.messages).toEqual([])
  })

  it('两形态同 store：一实例更新消息，另一实例可见（§3.1B 不分裂会话）', async () => {
    const { result: floating } = renderHook(() => useChatState())
    const { result: fullPage } = renderHook(() => useChatState())

    const userMsg = makeUserMessage('帮我生成一份测试报告')
    act(() => {
      floating.current.updateMessages((prev) => [...prev, userMsg])
    })

    // 共享单一会话实例：整页形态立即看到浮窗写入的消息
    expect(fullPage.current.messages).toEqual([userMsg])
    expect(floating.current.messages).toEqual([userMsg])

    // 500ms 防抖持久化到 iatp:ai-chat:v1:messages（单写入点）
    await waitFor(() => {
      expect(aiChatPrefs.loadMessages()?.map((m) => m.key)).toContain(userMsg.key)
    })
  })
})
