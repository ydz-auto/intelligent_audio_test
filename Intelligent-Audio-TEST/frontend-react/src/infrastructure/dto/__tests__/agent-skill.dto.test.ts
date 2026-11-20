import { describe, expect, it } from 'vitest'

import {
  toAgentSkill,
  toSkillDraftRequest,
  toSkillGate,
  toSkillPublishResult,
  toSkillTools,
  toSkillVersions,
  type AgentSkillViewDto,
} from '@/infrastructure/dto/agentSkill.dto'

const RAW: AgentSkillViewDto = {
  id: 's-1',
  scope: 'USER',
  name: 'task-diagnose-copy',
  description: '任务诊断：失败原因定位。触发词：任务失败、日志诊断。',
  version: '3',
  status: 'DRAFT',
  content_hash: 'abcdef0123456789',
  masked_by: null,
  owner: 'dev_user',
  owner_id: 7,
  tenant_id: 'default',
  created_by: 7,
  updated_at: '2026-11-14T01:02:03',
  allowed_tools: ['task_query', 'tool_search'],
  permissions: ['task:read'],
  budgets: { maxToolCalls: 20 },
  issues: [
    {
      code: 'MISSING_REQUIRED_SECTION',
      severity: 'ERROR',
      field: 'body',
      message: '正文缺少 `## Gotchas` 一节',
    },
  ],
}

describe('toAgentSkill', () => {
  it('snake_case → camelCase，并补 UTC 时区', () => {
    const skill = toAgentSkill(RAW)
    expect(skill).toMatchObject({
      id: 's-1',
      scope: 'USER',
      name: 'task-diagnose-copy',
      version: '3',
      status: 'DRAFT',
      contentHash: 'abcdef0123456789',
      maskedBy: null,
      allowedTools: ['task_query', 'tool_search'],
      permissions: ['task:read'],
      budgets: { maxToolCalls: 20 },
      updatedAt: '2026-11-14T01:02:03Z',
    })
    expect(skill.issues[0]).toMatchObject({
      code: 'MISSING_REQUIRED_SECTION',
      severity: 'ERROR',
      field: 'body',
    })
  })

  it('masked_by 与非法枚举归一：未知来源按 PLATFORM，未知状态按 DRAFT', () => {
    const skill = toAgentSkill({
      ...RAW,
      scope: 'SOMETHING',
      status: 'WHATEVER',
      masked_by: 'USER',
    })
    expect(skill.scope).toBe('PLATFORM')
    expect(skill.status).toBe('DRAFT')
    expect(skill.maskedBy).toBe('USER')
  })

  it('已有带时区的时间戳不重复追加 Z', () => {
    const skill = toAgentSkill({
      ...RAW,
      updated_at: '2026-11-14T01:02:03+08:00',
    })
    expect(skill.updatedAt).toBe('2026-11-14T01:02:03+08:00')
  })
})

describe('toSkillDraftRequest', () => {
  it('只发草稿内容字段，frontmatter 原样携带（身份字段不出现）', () => {
    const request = toSkillDraftRequest({
      name: 'demo-skill',
      description: '说明',
      frontmatter: { 'allowed-tools': ['task_query'], permissions: [] },
      body: '## Gotchas\n\n## 验收\n',
    })
    expect(request).toEqual({
      name: 'demo-skill',
      description: '说明',
      body: '## Gotchas\n\n## 验收\n',
      frontmatter: { 'allowed-tools': ['task_query'], permissions: [] },
    })
    expect(request).not.toHaveProperty('scope')
    expect(request).not.toHaveProperty('owner_id')
  })
})

describe('tools / versions / gate', () => {
  it('工具清单转 camelCase 并保留 enabled', () => {
    expect(
      toSkillTools([
        { name: 'task_query', description: '查任务', risk: 'READ', permissions: ['task:read'], enabled: true },
        { name: 'task_run', description: '跑任务', risk: 'WRITE', permissions: ['task:execute'], enabled: false },
      ])
    ).toEqual([
      {
        name: 'task_query',
        description: '查任务',
        risk: 'READ',
        permissions: ['task:read'],
        enabled: true,
      },
      {
        name: 'task_run',
        description: '跑任务',
        risk: 'WRITE',
        permissions: ['task:execute'],
        enabled: false,
      },
    ])
  })

  it('版本历史转 camelCase + UTC 归一', () => {
    const versions = toSkillVersions({
      items: [
        { version: '2', content_hash: 'aa', created_at: '2026-11-14T00:00:00', created_by: 7 },
      ],
    })
    expect(versions).toEqual([
      {
        version: '2',
        contentHash: 'aa',
        createdAt: '2026-11-14T00:00:00Z',
        createdBy: 7,
      },
    ])
  })

  it('门槛结果缺字段时给安全默认值', () => {
    expect(toSkillGate(undefined)).toEqual({
      goldenTasks: 0,
      passed: false,
      failures: [],
      note: '',
    })
  })

  it('发布结果拆 { skill, gate, participates_in_trigger }', () => {
    const result = toSkillPublishResult({
      skill: RAW,
      gate: {
        golden_tasks: 3,
        passed: false,
        failures: ['触发判定未通过'],
        note: '命中拒绝、未命中不等于安全',
      },
      participates_in_trigger: false,
    })
    expect(result.skill.status).toBe('DRAFT')
    expect(result.gate).toEqual({
      goldenTasks: 3,
      passed: false,
      failures: ['触发判定未通过'],
      note: '命中拒绝、未命中不等于安全',
    })
    expect(result.participatesInTrigger).toBe(false)
  })
})
