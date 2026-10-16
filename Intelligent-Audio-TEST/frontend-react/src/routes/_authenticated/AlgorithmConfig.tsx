import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { PagePlaceholder } from '@/features/placeholder/page-placeholder'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 算法配置 /AlgorithmConfig（侧栏「测试配置」组，INT-417 提升）。
 * 页面本体随 INT-362（配置运维域算法配置规范）落地；本卡出导航落位占位。
 * beforeLoad：algorithm:read 守卫 → 无码整页 /403。
 */
export const Route = createFileRoute('/_authenticated/AlgorithmConfig')({
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'algorithm:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: () => (
    <PagePlaceholder
      title='算法配置'
      note='算法定义/分组管理页面随 INT-362 卡落地'
    />
  ),
})
