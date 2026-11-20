/**
 * Skill 列表行内动作集合（INT-2607）。
 *
 * 缺陷：TENANT 共享 Skill 行也渲染「删除」，点进二次确认后服务端恒 409
 * （`agent_service/application/skill_service.py`：TENANT 共享 Skill 不支持删除）。
 * 动作按来源分层：PLATFORM 只 fork / 导出；TENANT 只导出（停用 / 审核由 TENANT
 * 前端卡补齐）；USER 编辑 / 停用 / 导出 / 删除。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  SKILL_SCOPE,
  SKILL_STATUS,
  type AgentSkill,
} from '@/domain/models/agentSkill'

import { AgentSkillList } from '@/features/agent-skills/components/agent-skill-list'

function skill(overrides: Partial<AgentSkill> = {}): AgentSkill {
  return {
    id: 'skill-1',
    scope: SKILL_SCOPE.USER,
    name: 'demo-skill',
    description: '演示用 Skill',
    version: '1',
    status: SKILL_STATUS.ACTIVE,
    contentHash: 'abcdef0123456789',
    maskedBy: null,
    owner: 'dev_user',
    ownerId: 1,
    allowedTools: [],
    permissions: [],
    budgets: {},
    updatedAt: '2026-11-14T00:00:00Z',
    issues: [],
    ...overrides,
  }
}

function renderList(skills: AgentSkill[]) {
  return render(
    <AgentSkillList
      busyAction={null}
      busySkillId={null}
      filtered={false}
      hasCustomSkills
      isError={false}
      isPending={false}
      onCreate={vi.fn()}
      onDelete={vi.fn()}
      onDisable={vi.fn()}
      onEdit={vi.fn()}
      onExport={vi.fn()}
      onFork={vi.fn()}
      onImport={vi.fn()}
      onRetry={vi.fn()}
      skills={skills}
    />
  )
}

function rowActionNames(): string[] {
  return screen
    .getAllByTestId('agent-skill-row')
    .flatMap((row) =>
      Array.from(row.querySelectorAll('button')).map(
        (button) => button.getAttribute('aria-label') || button.textContent || ''
      )
    )
}

describe('AgentSkillList 行内动作按来源分层（INT-2607）', () => {
  it('TENANT 共享行不展示「删除」，只保留导出', () => {
    renderList([skill({ scope: SKILL_SCOPE.TENANT, owner: 'tenant' })])

    expect(screen.queryByRole('button', { name: /删除/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /编辑/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /停用/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /fork/ })).toBeNull()
    expect(screen.getByRole('button', { name: /导出/ })).toBeInTheDocument()
  })

  it('USER 行保留编辑 / 停用 / 导出 / 删除（修复不误伤本人 Skill）', () => {
    renderList([skill({ scope: SKILL_SCOPE.USER })])

    const actions = rowActionNames().join('|')
    expect(actions).toContain('编辑')
    expect(actions).toContain('停用')
    expect(actions).toContain('导出')
    expect(actions).toContain('删除')
  })

  it('PLATFORM 行只有 fork / 导出，不展示删除', () => {
    renderList([skill({ scope: SKILL_SCOPE.PLATFORM, owner: 'platform' })])

    const actions = rowActionNames().join('|')
    expect(actions).toContain('fork')
    expect(actions).toContain('导出')
    expect(actions).not.toContain('删除')
    expect(actions).not.toContain('编辑')
  })
})
