import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { EvaluationPage } from '@/features/evaluation/evaluation-page'

/**
 * 评估维度 /Evaluation（侧栏「测试配置」组，INT-417 提升）。
 * 11_用例域.md §4.1：列表/分组双视图 + 维度/分类/权重/规则（本卡 INT-509 替换占位路由）。
 * beforeLoad：evaluation:read 守卫 → 无码整页 /403?from。
 */
export const Route = createFileRoute('/_authenticated/Evaluation')({
  beforeLoad: ({ location }) => {
    requirePermission('evaluation:read', location)
  },
  component: EvaluationPage,
})
