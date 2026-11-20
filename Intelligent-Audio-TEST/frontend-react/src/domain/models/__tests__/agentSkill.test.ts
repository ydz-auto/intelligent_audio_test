import { describe, expect, it } from 'vitest'

import {
  SKILL_STATUS,
  SKILL_SCOPE,
  emptySkillDraft,
  isDisableableSkill,
  isPublishableSkill,
  isValidSkillName,
  isWritableSkill,
  missingRequiredSections,
  skillPackageFilename,
  shortContentHash,
  type AgentSkill,
} from '@/domain/models/agentSkill'

function makeSkill(overrides: Partial<AgentSkill> = {}): AgentSkill {
  return {
    id: 's-1',
    scope: SKILL_SCOPE.USER,
    name: 'demo',
    description: '说明',
    version: '2',
    status: SKILL_STATUS.DRAFT,
    contentHash: 'abcdef0123456789',
    maskedBy: null,
    owner: 'dev_user',
    ownerId: 7,
    allowedTools: [],
    permissions: [],
    budgets: {},
    updatedAt: null,
    issues: [],
    ...overrides,
  }
}

describe('Skill 名称口径', () => {
  it('接受小写字母 / 数字 / 连字符且 2~64 位', () => {
    expect(isValidSkillName('ab')).toBe(true)
    expect(isValidSkillName('task-diagnose-copy')).toBe(true)
    expect(isValidSkillName('a1-2b')).toBe(true)
  })

  it('拒绝大写 / 下划线 / 单字符 / 首尾非法 / 超长', () => {
    expect(isValidSkillName('My_Skill')).toBe(false)
    expect(isValidSkillName('a')).toBe(false)
    expect(isValidSkillName('-abc')).toBe(false)
    // 后端正则 ^[a-z0-9][a-z0-9-]{1,63}$ 允许内部/结尾连字符，只是不能以连字符开头
    expect(isValidSkillName('abc-2')).toBe(true)
    expect(isValidSkillName('a'.repeat(65))).toBe(false)
  })
})

describe('正文必需小节', () => {
  it('缺 Gotchas / 验收时逐项返回', () => {
    expect(missingRequiredSections('## 步骤\n内容')).toEqual(['Gotchas', '验收'])
    expect(
      missingRequiredSections('## Gotchas\n- 无\n\n## 验收\n- 通过')
    ).toEqual([])
  })
})

describe('Skill 行操作可用性', () => {
  it('平台内置只读：不可编辑 / 发布 / 停用', () => {
    const platform = makeSkill({ scope: SKILL_SCOPE.PLATFORM })
    expect(isWritableSkill(platform)).toBe(false)
    expect(isPublishableSkill(platform)).toBe(false)
    expect(isDisableableSkill(platform)).toBe(false)
  })

  it('USER 草稿可编辑 / 发布；已发布不可再发布但可停用', () => {
    expect(isPublishableSkill(makeSkill())).toBe(true)
    const active = makeSkill({ status: SKILL_STATUS.ACTIVE })
    expect(isPublishableSkill(active)).toBe(false)
    expect(isDisableableSkill(active)).toBe(true)
    expect(isDisableableSkill(makeSkill({ status: SKILL_STATUS.DISABLED }))).toBe(false)
  })
})

describe('展示口径', () => {
  it('contentHash 只展示前 8 位', () => {
    expect(shortContentHash('abcdef0123456789')).toBe('abcdef01')
    expect(shortContentHash('')).toBe('—')
  })

  it('导出文件名 <name>-v<version>.zip', () => {
    expect(skillPackageFilename({ name: 'demo', version: '3' })).toBe('demo-v3.zip')
  })

  it('空草稿带 name / description / frontmatter 与正文骨架', () => {
    const draft = emptySkillDraft()
    expect(draft.name).toBe('')
    expect(draft.body).toContain('## Gotchas')
    expect(draft.body).toContain('## 验收')
    expect(draft.frontmatter).toEqual({ 'allowed-tools': [], permissions: [] })
  })
})
