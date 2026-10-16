import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { PagePlaceholder } from '@/features/placeholder/page-placeholder'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 评估维度 /Evaluation（侧栏「测试配置」组，INT-417 提升）。
 * 页面本体随 INT-356（用例域 §4.1）落地；本卡出导航落位占位。
 * beforeLoad：evaluation:read 守卫 → 无码整页 /403。
 */
export const Route = createFileRoute('/_authenticated/Evaluation')({
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'evaluation:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: () => (
    <PagePlaceholder
      title='评估维度'
      note='评估维度与分类管理页面随 INT-356 卡落地'
    />
  ),
})
