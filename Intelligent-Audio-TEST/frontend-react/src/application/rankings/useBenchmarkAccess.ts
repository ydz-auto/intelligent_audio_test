/**
 * 排行页权限上下文（application 层，INT-344 公开页口径 + 现状部署特例）。
 * AUTH_MODE=off（现状部署 mock）：未登录访客全员放行（中间件注入 ['*']，
 * 14_benchmark排行.md §6.1）——公开页可视稿首屏不空；已登录用户按真实权限码判定，
 * RBAC 分支（无 benchmark:ranking:read → 数据 403 空态；无 compute → 按钮隐藏）仍可演示。
 */
import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

export interface BenchmarkAccess {
  /** 读榜（benchmark:ranking:read）——false 时页面数据 403 空态 */
  canRead: boolean
  /** 触发重算（benchmark:ranking:compute）——false 时「立即计算」隐藏 */
  canCompute: boolean
  /** 查看报告（report:read）——false 时行尾「查看报告」链接隐藏 */
  canReadReport: boolean
  /** 算法定义（algorithm:read）——false 时算法网格只读降级条 */
  canReadAlgorithm: boolean
}

export function useBenchmarkAccess(): BenchmarkAccess {
  const user = useAuthStore((s) => s.user)
  // AUTH_MODE=off 开放模式：启动引导已把后端注入的 dev_user（permissions=['*']）
  // 回填 store，hasPermission 通配即放行，无需在此为未登录特判；
  // 真实认证模式（dev/prod）未登录访客 user=null → 无权限 → 数据 403 空态
  // （14_benchmark排行.md §5.1/§6.2，INT-1225：匿名不再被整页跳登录，URL 直达
  // 时榜单/算法降级为权限空态 + 只读降级条）。
  return {
    canRead: hasPermission(user, 'benchmark:ranking:read'),
    canCompute: hasPermission(user, 'benchmark:ranking:compute'),
    canReadReport: hasPermission(user, 'report:read'),
    canReadAlgorithm: hasPermission(user, 'algorithm:read'),
  }
}
