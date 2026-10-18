import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { AlgorithmConfigPage } from '@/features/algorithm-config'

/**
 * 算法配置 /AlgorithmConfig（侧栏「测试配置」组，INT-417 提升）。
 * 17_配置运维.md §3 全量可视稿：列表/详情/编辑 Sheet/分组管理/导入/导出/重载/批量删除；
 * 全局算法切换器数据源本体（§2.2）。本卡替换占位路由为完整实现（INT-508）。
 * beforeLoad：algorithm:read 守卫 → 无码整页 /403?from。
 */
export const Route = createFileRoute('/_authenticated/AlgorithmConfig')({
  beforeLoad: ({ location }) => {
    requirePermission('algorithm:read', location)
  },
  component: AlgorithmConfigPage,
})
