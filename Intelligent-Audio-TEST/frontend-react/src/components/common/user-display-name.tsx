import { useUserDisplayName } from '@/application/users/use-user-display-name'

interface UserDisplayNameProps {
  userId?: number | null
  className?: string
}

/**
 * 用户 ID → 显示名（创建人/更新人等卡片元信息统一入口）。
 * 姓名经 application 层 useUserDisplayName 解析；无权限/失败回退「用户#id」，空 id 显示「—」。
 */
export function UserDisplayName({ userId, className }: UserDisplayNameProps) {
  const name = useUserDisplayName(userId)
  if (userId == null) return <span className={className}>—</span>
  return <span className={className}>{name ?? `用户#${userId}`}</span>
}
