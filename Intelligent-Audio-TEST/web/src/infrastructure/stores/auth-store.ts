import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { AuthUser } from '@/domain/models/user'

/**
 * mock 会话 store（infrastructure 层；红线④：不接真实后端）。
 * TODO(API 接线): setAuth 改为真实登录/登出接口回写（见 infrastructure/api/auth.ts）。
 */

type AuthState = {
  user: AuthUser | null
  setAuth: (user: AuthUser | null) => void
}

/** mock 演示用户：超级管理员，permissions '*' 全通过（04_控制台.md §5 矩阵验证用） */
export const MOCK_USER: AuthUser = {
  id: 'mock-user-001',
  username: 'demo_admin',
  displayName: '演示管理员',
  roleName: '超级管理员',
  permissions: ['*'],
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      setAuth: (user) => set({ user }),
    }),
    {
      name: 'iatp:auth:v1',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

/** mock 登录：演示环境任意账号密码均可进入 */
export function mockLogin(username: string): AuthUser {
  return {
    ...MOCK_USER,
    username,
    displayName:
      username === MOCK_USER.username ? MOCK_USER.displayName : username,
  }
}
