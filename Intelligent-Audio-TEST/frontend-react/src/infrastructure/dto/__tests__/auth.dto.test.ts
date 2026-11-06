/**
 * auth DTO 单测（角色名映射，INT-1226）：
 * - toAuthUser：登录响应 role_name（角色码）→ ROLE_META 中文名（admin→超级管理员…）；
 *   未知码/空串沿用原值。
 * - toAuthUserFromMe：/auth/me 契约缺 role_name，roleName 由 fallbackRoleName 兜底，
 *   同样照 ROLE_META 映射中文名，不因缺字段清空。
 */
import { describe, expect, it } from 'vitest'

import {
  toAuthUser,
  toAuthUserFromMe,
} from '@/infrastructure/dto/auth.dto'

describe('auth.dto 角色名映射（INT-1226）', () => {
  describe('toAuthUser（登录响应）', () => {
    it('admin → 超级管理员', () => {
      const user = toAuthUser({
        id: 1,
        username: 'admin',
        role_id: 1,
        role_name: 'admin',
        permissions: ['*'],
      })
      expect(user.roleName).toBe('超级管理员')
    })

    it('tester → 测试工程师', () => {
      const user = toAuthUser({
        id: 2,
        username: 'tester',
        role_id: 2,
        role_name: 'tester',
        permissions: ['task:read'],
      })
      expect(user.roleName).toBe('测试工程师')
    })

    it('未知角色码沿用原码', () => {
      const user = toAuthUser({
        id: 3,
        username: 'custom',
        role_id: 9,
        role_name: '自定义角色',
        permissions: [],
      })
      expect(user.roleName).toBe('自定义角色')
    })

    it('role_name 空串 → 空串', () => {
      const user = toAuthUser({
        id: 4,
        username: 'x',
        role_id: null,
        role_name: '',
        permissions: [],
      })
      expect(user.roleName).toBe('')
    })
  })

  describe('toAuthUserFromMe（/auth/me 会话恢复）', () => {
    it('fallback 传角色码 → 映射中文名', () => {
      const user = toAuthUserFromMe(
        { user_id: 369, username: '接线测试_admin', role_id: 1, permissions: ['*'] },
        'admin'
      )
      expect(user.username).toBe('接线测试_admin')
      expect(user.roleName).toBe('超级管理员')
    })

    it('fallback 已是中文名 → 原样保留', () => {
      const user = toAuthUserFromMe(
        { user_id: 370, username: '接线测试_tester', role_id: 2, permissions: [] },
        '测试工程师'
      )
      expect(user.roleName).toBe('测试工程师')
    })

    it('无 fallback → 空串（不显示错角色，个人中心取不到显示「—」）', () => {
      const user = toAuthUserFromMe({
        user_id: 373,
        username: '接线测试_guest',
        role_id: 5,
        permissions: ['home:read'],
      })
      expect(user.roleName).toBe('')
    })
  })
})
