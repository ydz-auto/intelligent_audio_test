/**
 * Skill 编辑器（INT-2550 打回修复）：
 * - 读取 SKILL.md 失败态的「重新加载」必须真的重发请求（旧实现只 setState，
 *   错误态下 state 已为 true，React 跳过更新 → 死按钮）；
 * - 保存成功只回显 WARNING 时，汇总文案不能再说「未保存」。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AgentSkill } from '@/domain/models/agentSkill'
import { SkillEditorDialog } from '@/features/agent-skills/components/skill-editor-dialog'

const refetchMock = vi.hoisted(() => vi.fn())
const updateMock = vi.hoisted(() => vi.fn())
const docState = vi.hoisted(() => ({
  current: {} as {
    data?: { frontmatterText: string; body: string }
    isPending: boolean
    isError: boolean
    refetch: () => void
  },
}))

vi.mock('@/application/agent/use-agent-skills', () => ({
  useAgentSkillDocumentQuery: () => docState.current,
  useAgentSkillVersionsQuery: () => ({ data: [], isPending: false }),
  useAgentSkillMutations: () => ({
    create: { isPending: false, mutateAsync: vi.fn() },
    update: { isPending: false, mutateAsync: updateMock },
    publish: { isPending: false, mutateAsync: vi.fn() },
    invalidateSkill: vi.fn(),
  }),
  skillErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

const SKILL: AgentSkill = {
  id: 'sk-1',
  scope: 'USER',
  name: 'probe-skill',
  description: '探针 Skill',
  version: '1',
  status: 'DRAFT',
  contentHash: 'abcdef0123456789',
  maskedBy: null,
  owner: 'dev_user',
  ownerId: 1,
  allowedTools: [],
  permissions: [],
  budgets: {},
  updatedAt: '2026-11-14T00:00:00Z',
  issues: [],
}

function renderEditor() {
  return render(
    <SkillEditorDialog
      onOpenChange={() => undefined}
      onSaved={() => undefined}
      open
      skill={SKILL}
      tools={[]}
    />
  )
}

describe('SkillEditorDialog（INT-2550 打回修复）', () => {
  it('文档错误态点「重新加载」会重发请求（不是死按钮）', () => {
    refetchMock.mockReset()
    docState.current = {
      isError: true,
      isPending: false,
      data: undefined,
      refetch: refetchMock,
    }

    renderEditor()

    const retry = screen.getByTestId('skill-doc-retry')
    fireEvent.click(retry)

    expect(refetchMock).toHaveBeenCalledTimes(1)
  })

  it('保存成功只剩 WARNING：汇总文案是「告警不阻塞保存」，不再说「未保存」', async () => {
    updateMock.mockReset()
    updateMock.mockResolvedValue({
      ...SKILL,
      version: '2',
      issues: [
        {
          code: 'EMBEDDED_SECRET',
          severity: 'WARNING',
          field: 'body',
          message: '正文含疑似凭证',
        },
      ],
    })
    docState.current = {
      isError: false,
      isPending: false,
      data: { frontmatterText: '', body: '## Gotchas\n\n## 验收\n' },
      refetch: vi.fn(),
    }

    renderEditor()

    fireEvent.change(screen.getByLabelText('正文（SKILL.md）'), {
      target: { value: '## Gotchas\n已处理\n## 验收\n已验' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(screen.getByTestId('skill-editor-issues')).toHaveTextContent(
        '告警不阻塞保存'
      )
    })
    expect(screen.getByTestId('skill-editor-issues')).not.toHaveTextContent(
      '未保存'
    )
  })
})
