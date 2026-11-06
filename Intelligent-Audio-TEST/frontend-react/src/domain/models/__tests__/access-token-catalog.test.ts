/**
 * Access Token 业务可暴露 scopes 目录测试（INT-1153/INT-1140 能力覆盖边界）：
 * 目录必须覆盖业务模块与 :share 数据可见性点，且不包含个人信息/系统设置除外项
 * （iam/auth/option/status/sse/log 管理类/通配）。
 */
import { describe, expect, it } from 'vitest'

import {
  ACCESS_TOKEN_SCOPE_CATALOG,
  ACCESS_TOKEN_SCOPE_FLAT,
} from '../access-token'

const codes = ACCESS_TOKEN_SCOPE_FLAT.map((p) => p.code)
const modules = ACCESS_TOKEN_SCOPE_CATALOG.map((m) => m.id)

describe('ACCESS_TOKEN_SCOPE_CATALOG（业务可暴露子集）', () => {
  it('覆盖业务域模块', () => {
    for (const module of [
      'task',
      'published_task',
      'testcase',
      'audio',
      'device',
      'playback',
      'spl',
      'digital_spl',
      'api_config',
      'report',
      'benchmark',
      'evaluation',
      'algorithm',
      'group',
      'tag',
      'lab',
    ]) {
      expect(modules).toContain(module)
    }
  })

  it('包含 :share 数据可见性分享点', () => {
    for (const code of [
      'task:share',
      'testcase:share',
      'audio:share',
      'report:share',
      'evaluation:share',
      'group:share',
      'tag:share',
    ]) {
      expect(codes).toContain(code)
    }
  })

  it('包含 data-transfer / report-studio 业务点', () => {
    expect(codes).toContain('task:export')
    expect(codes).toContain('task:import')
    expect(codes).toContain('report:studio:create')
    expect(codes).toContain('report:studio:export')
  })

  it('log 域只读覆盖、管理类除外', () => {
    expect(codes).toContain('log:read')
    expect(codes).not.toContain('log:manage')
    expect(codes).not.toContain('log:websocket')
  })

  it('除外：个人信息 / 系统设置 / 长连接不暴露', () => {
    for (const excluded of [
      'user:read',
      'role:read',
      'permission:read',
      'auth:manage_provider',
      'auth:me',
      'auth:login',
      'option:read',
      'option:write',
      'status:read',
      'sse:read',
      '*',
    ]) {
      expect(codes).not.toContain(excluded)
    }
  })

  it('目录码唯一', () => {
    expect(new Set(codes).size).toBe(codes.length)
  })
})
