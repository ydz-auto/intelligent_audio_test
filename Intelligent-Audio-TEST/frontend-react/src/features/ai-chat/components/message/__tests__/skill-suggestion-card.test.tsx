/**
 * 「沉淀为 Skill」建议卡（INT-2550 / INT-2584）：
 * - 文案与工具清单来自事件载荷（不伪造）；
 * - 主按钮带 `?name=&description=` 直达 /agent-skills 预填新建；
 * - 「忽略」只回调关闭（无请求、无跳转），created=true 时只剩徽标与忽略。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ChatSkillSuggestion } from '@/domain/models/aiChat'
import { SkillSuggestionCard } from '@/features/ai-chat/components/message/skill-suggestion-card'

// 测试不挂 RouterProvider：Link 降级为普通 <a>，search 拼进 href 便于断言跳转契约
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({
      children,
      search,
      to,
      ...props
    }: React.ComponentProps<'a'> & {
      search?: Record<string, unknown>
      to?: string
    }) => {
      const query = new URLSearchParams()
      for (const [key, value] of Object.entries(search ?? {})) {
        if (value !== undefined && value !== null) query.set(key, String(value))
      }
      const qs = query.toString()
      return (
        <a href={`${to}${qs ? `?${qs}` : ''}`} {...props}>
          {children}
        </a>
      )
    },
  }
})

const suggestion: ChatSkillSuggestion = {
  suggestedName: 'platform-contract-tool-search',
  description: '基于本次 run 的执行流程沉淀的 Skill 草案',
  toolsUsed: ['platform_contract', 'tool_search'],
  created: false,
  requiresConfirmation: true,
}

describe('SkillSuggestionCard', () => {
  it('渲染建议名 / 工具清单 / 不自动落库说明', () => {
    render(<SkillSuggestionCard suggestion={suggestion} />)

    expect(screen.getByText('沉淀为 Skill')).toBeInTheDocument()
    expect(screen.getByText('platform-contract-tool-search')).toBeInTheDocument()
    expect(screen.getByText('platform_contract')).toBeInTheDocument()
    expect(screen.getByText('tool_search')).toBeInTheDocument()
    expect(screen.getByText(/不自动落库、不自动触发/)).toBeInTheDocument()
    expect(screen.getByText(/调用了 2 个工具/)).toBeInTheDocument()
  })

  it('「去创建草稿」带 name / description 直达 Skill 管理页（仅跳转，不创建）', () => {
    render(<SkillSuggestionCard suggestion={suggestion} />)

    const create = screen.getByTestId('skill-suggestion-create')
    const href = create.getAttribute('href') ?? ''
    expect(href.startsWith('/agent-skills?')).toBe(true)
    const params = new URLSearchParams(href.slice(href.indexOf('?') + 1))
    expect(params.get('name')).toBe(suggestion.suggestedName)
    expect(params.get('description')).toBe(suggestion.description)
  })

  it('「忽略」只回调关闭：不发请求、不改页面其他内容', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const onDismiss = vi.fn()
    render(
      <SkillSuggestionCard onDismiss={onDismiss} suggestion={suggestion} />
    )

    await userEvent.click(screen.getByTestId('skill-suggestion-dismiss'))

    expect(onDismiss).toHaveBeenCalledTimes(1)
    expect(fetchSpy).not.toHaveBeenCalled()
    // 卡片本身仍由消息层决定是否渲染（这里只是回调，不做本地隐藏）
    expect(screen.getByTestId('skill-suggestion-card')).toBeInTheDocument()
    fetchSpy.mockRestore()
  })

  it('created=true：显示「已创建」徽标，不再给创建入口，忽略仍可用', () => {
    render(
      <SkillSuggestionCard
        onDismiss={vi.fn()}
        suggestion={{ ...suggestion, created: true }}
      />
    )

    expect(screen.getByText('已创建')).toBeInTheDocument()
    expect(screen.queryByTestId('skill-suggestion-create')).not.toBeInTheDocument()
    expect(screen.getByTestId('skill-suggestion-dismiss')).toBeInTheDocument()
  })
})
