import { createFileRoute } from '@tanstack/react-router'

import { requireAnyPermission } from '@/application/auth/route-guards'
import { SplMappingPage } from '@/features/spl-mapping'

/**
 * SPL 映射 /SPLMapping（侧栏「测试配置」组，INT-417 提升；16_设备域.md §4）。
 * 页面本体 INT-506 落地：SectionPageLayout + 双口径页签 + 物理/数字域 DataTable +
 * 校准族弹窗（§6.7-6.12/§6.22）+ 三口径对称提示。
 * beforeLoad：spl:read 或 digital_spl:read（任一，INT-417 口径）→ 无码整页 /403?from。
 */
export const Route = createFileRoute('/_authenticated/SPLMapping')({
  beforeLoad: ({ location }) => {
    requireAnyPermission(['spl:read', 'digital_spl:read'], location)
  },
  component: SplMappingPage,
})
