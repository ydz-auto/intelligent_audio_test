/**
 * algo_engineer 只读观察判定（application 层；10_测试执行.md §3.1.1/§7）。
 * 进入与守卫：持有 task:execute 走完整交互态；algo_engineer（无 task:execute、
 * 按 INT-449 只读权限点判定）走只读观察态；其余无权限角色（device_admin/guest）
 * 仍整页 /403（路由 beforeLoad 分支处理）。
 * 只读态随权限快照响应式更新，全页动作钮/控制/提交投影隐藏。
 */
import { usePermissions } from '@/application/hooks/use-permissions'

export function useReadOnlyMode(): boolean {
  const { hasPermission } = usePermissions()
  const hasExecute = hasPermission('task:execute')
  const hasReadOnlyPoint = hasPermission('algorithm:read')
  // INT-449 后端只读权限点尚未落地：algo_engineer 以 algorithm:read 标识（§7 矩阵）
  return !hasExecute && hasReadOnlyPoint
}
