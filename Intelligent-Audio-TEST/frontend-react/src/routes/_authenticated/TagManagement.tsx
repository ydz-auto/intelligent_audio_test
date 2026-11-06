import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { TagManagementPage } from '@/features/tags/tags-page'

/**
 * 标签管理 /TagManagement（侧栏「测试配置」组，INT-417 提升）。
 * 11_用例域.md §4.2：左分类树 + 右标签表（categoryName 分组、INT-487 标签带分类）；
 * TagEdit/TagCategory 模态窗随 §5.4。本卡替换占位路由为完整可视稿。
 * beforeLoad：tag:read 守卫 → 无码整页 /403?from。
 */
export const Route = createFileRoute('/_authenticated/TagManagement')({
  beforeLoad: ({ location }) => {
    requirePermission('tag:read', location)
  },
  component: TagManagementPage,
})
