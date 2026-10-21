/**
 * Access Token scopes 勾选目录测试（INT-1155）
 * 验证业务可暴露子集与 INT-1140「能力覆盖清单」一致：业务域齐全、data-transfer 与 *:share 在列、
 * 日志只读倾向（仅 log:read）、除外域（个人信息 / 系统设置 / SSE / 站点状态）不在列。
 */
import { describe, it, expect } from 'vitest'
import {
  ACCESS_TOKEN_SCOPE_GROUPS,
  ALL_ACCESS_TOKEN_SCOPES,
  accessTokenScopeLabel,
} from '../accessTokenScopes'

describe('ACCESS_TOKEN_SCOPE_GROUPS（INT-1155 业务可暴露子集）', () => {
  it('覆盖 INT-1140 能力覆盖清单的各业务域', () => {
    const modules = ACCESS_TOKEN_SCOPE_GROUPS.map((g) => g.module)
    const expected = [
      'task',
      'published_task',
      'testcase',
      'audio',
      'device',
      'playback',
      'spl',
      'digital_spl',
      'api_config',
      'lab',
      'report',
      'report-studio',
      'benchmark',
      'evaluation',
      'algorithm',
      'group',
      'tag',
      'logs',
    ]
    for (const mod of expected) {
      expect(modules).toContain(mod)
    }
  })

  it('data-transfer（task:export/import）与 *:share 数据可见性分享点已含', () => {
    const all = ALL_ACCESS_TOKEN_SCOPES
    expect(all).toContain('task:export')
    expect(all).toContain('task:import')
    for (const share of [
      'task:share',
      'testcase:share',
      'audio:share',
      'report:share',
      'evaluation:share',
      'group:share',
      'tag:share',
    ]) {
      expect(all).toContain(share)
    }
  })

  it('日志域只读倾向覆盖：仅 log:read；管理类 / 长连接推送除外', () => {
    const all = ALL_ACCESS_TOKEN_SCOPES
    expect(all).toContain('log:read')
    expect(all).not.toContain('log:manage')
    expect(all).not.toContain('log:websocket')
  })

  it('除外域不在列：个人信息 / 系统设置 / SSE / 站点状态', () => {
    const all = ALL_ACCESS_TOKEN_SCOPES
    for (const code of [
      'user:read',
      'user:create',
      'role:read',
      'permission:read',
      'auth:manage_provider',
      'option:read',
      'option:write',
      'auth:me',
      'auth:login',
      'auth:callback',
      'auth:refresh',
      'auth:logout',
      'sse:read',
      'status:read',
    ]) {
      expect(all).not.toContain(code)
    }
  })

  it('权限码唯一且均带中文释义', () => {
    const all = ALL_ACCESS_TOKEN_SCOPES
    expect(new Set(all).size).toBe(all.length)
    for (const group of ACCESS_TOKEN_SCOPE_GROUPS) {
      expect(group.label).toBeTruthy()
      for (const item of group.scopes) {
        expect(item.code).toBeTruthy()
        expect(item.label).toBeTruthy()
      }
    }
  })

  it('accessTokenScopeLabel：目录内返回释义，目录外原样返回', () => {
    expect(accessTokenScopeLabel('task:read')).toBe('查看任务')
    expect(accessTokenScopeLabel('log:read')).toBe('查看日志/统计/归档')
    expect(accessTokenScopeLabel('unknown:code')).toBe('unknown:code')
  })
})
