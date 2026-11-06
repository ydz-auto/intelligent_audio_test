/**
 * 当前用户用例 hook（application 层，13_个人中心.md §7）。
 * /auth/me 契约（auth_bp.py:183-186 实测）：{ user_id, username, role_id, permissions }
 * ——无 email、无 roleName；roleName 由前端 auth store 会话缓存兜底（authStore.ts:126）。
 * mock 会话即 zustand persist 的 AuthUser（红线④），角色名兜底语义与接线后一致。
 * TODO(API 接线): 登录时拉 /auth/me 落 authStore；本 hook 保持读取 store 不变。
 */
import type { ProfileUserInfo } from '@/domain/models/profile'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

export function useCurrentUser(): { user: ProfileUserInfo | null } {
  const authUser = useAuthStore((s) => s.user)

  const user: ProfileUserInfo | null = authUser
    ? {
        id: authUser.id,
        username: authUser.username,
        roleName: authUser.roleName,
        permissions: authUser.permissions,
      }
    : null

  return { user }
}
