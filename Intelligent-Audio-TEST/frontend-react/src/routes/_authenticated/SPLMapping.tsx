import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { PagePlaceholder } from '@/features/placeholder/page-placeholder'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * SPL 映射 /SPLMapping（侧栏「测试配置」组，INT-417 提升）。
 * 页面本体随 INT-361（设备域）落地；本卡出导航落位占位。
 * beforeLoad：spl:read 且 digital_spl:read（任一，INT-347 口径）→ 无码整页 /403。
 */
export const Route = createFileRoute('/_authenticated/SPLMapping')({
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'spl:read') && !hasPermission(user, 'digital_spl:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: () => (
    <PagePlaceholder
      title='SPL 映射'
      note='物理域+数字域双口径映射页面随 INT-361 卡落地'
    />
  ),
})
