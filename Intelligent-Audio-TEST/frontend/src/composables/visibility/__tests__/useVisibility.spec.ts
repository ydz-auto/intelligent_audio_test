/**
 * INT-467（UX 审计 P3）：可见性前端逻辑单测。
 *
 * 锁定契约：
 * 1. getVisibilityPref 缺省 shared；非法 localStorage 值回落 shared；setVisibilityPref 落偏好；
 * 2. canEditResource：共享恒放行 / 私有仅 owner（owner 缺失=开发态放行）/ admin 豁免
 *    （INT-467 代码审计 P2-1：对齐后端 §4.6「admin 跨过 owner/visibility 全量可操作」）；
 * 3. isOwner / isAdminUser 依 authStore 状态判定。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/store/authStore'
import {
  getVisibilityPref,
  setVisibilityPref,
  isAdminUser,
  isOwner,
  canEditResource,
  VISIBILITY_PREF_KEY,
} from '../useVisibility'
import { Visibility } from '@/domain/enums'

const USER_ID = 42

function authAs(user: { id?: number | null; permissions?: string[] } | null) {
  const store = useAuthStore()
  if (user) {
    store.setAuth('t', {
      id: user.id ?? 0,
      username: 'tester',
      roleId: null,
      roleName: '',
      permissions: user.permissions ?? [],
    })
  } else {
    store.logout()
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})

afterEach(() => {
  localStorage.clear()
})

describe('getVisibilityPref / setVisibilityPref', () => {
  it('无偏好时缺省 shared', () => {
    expect(getVisibilityPref()).toBe(Visibility.SHARED)
  })

  it('setVisibilityPref 后读回一致', () => {
    setVisibilityPref(Visibility.PRIVATE)
    expect(getVisibilityPref()).toBe(Visibility.PRIVATE)
  })

  it('非法 localStorage 值回落 shared', () => {
    localStorage.setItem(VISIBILITY_PREF_KEY, 'everyone')
    expect(getVisibilityPref()).toBe(Visibility.SHARED)
  })
})

describe('isAdminUser', () => {
  it('permissions 含 * 为管理员（AUTH_MODE=off 后端注入）', () => {
    authAs({ id: USER_ID, permissions: ['*'] })
    expect(isAdminUser()).toBe(true)
  })

  it('无 * 通配不是管理员', () => {
    authAs({ id: USER_ID, permissions: ['task:read'] })
    expect(isAdminUser()).toBe(false)
  })
})

describe('isOwner', () => {
  it('createdByUserId 与当前用户 id 一致为 owner', () => {
    authAs({ id: USER_ID })
    expect(isOwner(USER_ID)).toBe(true)
  })

  it('createdByUserId 与当前用户 id 不一致非 owner', () => {
    authAs({ id: USER_ID })
    expect(isOwner(USER_ID + 1)).toBe(false)
  })

  it('createdByUserId 缺失非 owner（缺省保护）', () => {
    authAs({ id: USER_ID })
    expect(isOwner(null)).toBe(false)
  })
})

describe('canEditResource', () => {
  it('null/undefined 资源不可编辑', () => {
    authAs({ id: USER_ID })
    expect(canEditResource(null)).toBe(false)
    expect(canEditResource(undefined)).toBe(false)
  })

  it('共享资源恒放行（回落既有权限点）', () => {
    authAs({ id: USER_ID })
    expect(canEditResource({ visibility: Visibility.SHARED, createdByUserId: 999 })).toBe(true)
    expect(canEditResource({ visibility: '', createdByUserId: 999 })).toBe(true)
  })

  it('私有资源：owner 可编辑', () => {
    authAs({ id: USER_ID })
    expect(canEditResource({ visibility: Visibility.PRIVATE, createdByUserId: USER_ID })).toBe(true)
  })

  it('私有资源：非 owner 不可编辑', () => {
    authAs({ id: USER_ID })
    expect(canEditResource({ visibility: Visibility.PRIVATE, createdByUserId: USER_ID + 1 })).toBe(false)
  })

  it('私有资源：owner 缺失按开发态放行（AUTH_MODE=off owner 列 NULL）', () => {
    authAs({ id: USER_ID })
    expect(canEditResource({ visibility: Visibility.PRIVATE, createdByUserId: null })).toBe(true)
  })

  it('私有资源：admin 豁免可编辑（INT-467 P2-1 对齐后端 §4.6）', () => {
    authAs({ id: USER_ID, permissions: ['*'] })
    expect(canEditResource({ visibility: Visibility.PRIVATE, createdByUserId: USER_ID + 1 })).toBe(true)
  })
})
