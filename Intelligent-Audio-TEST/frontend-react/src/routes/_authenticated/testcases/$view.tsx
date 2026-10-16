import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import {
  TEST_CASES_TAB_WHITELIST,
  type TestCasesViewKey,
} from '@/features/testcases/constants'
import { TestCasesPage } from '@/features/testcases'

/**
 * /testcases/$view 双视图（by-group 分组 / by-tag 标签），11_用例域.md §3.2。
 * beforeLoad：白名单校验（非法回 by-group）+ testcase:read 守卫 → 无码 /403。
 * validateSearch（zod + .catch()，URL 化可分享/回退）：page/pageSize/search/group/
 * tag（多选数组）/dimensionId/favorite/trash——mock 态为可分享参数，接线后接 useTableUrlState。
 * INT-486 用例不分类型口径：type（api/e2e）URL 参数移除——用例无类型之分。
 */
const testcasesSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(20),
  search: z.string().optional().catch(undefined),
  group: z.string().optional().catch(undefined),
  tag: z.array(z.string()).optional().catch(undefined),
  dimensionId: z.number().optional().catch(undefined),
  favorite: z.boolean().optional().catch(undefined),
  trash: z.boolean().optional().catch(undefined),
})

export const Route = createFileRoute('/_authenticated/testcases/$view')({
  beforeLoad: ({ params }) => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'testcase:read')) {
      throw redirect({ to: '/403' })
    }
    if (!TEST_CASES_TAB_WHITELIST.includes(params.view)) {
      throw redirect({
        to: '/testcases/$view',
        params: { view: 'by-group' },
      })
    }
  },
  validateSearch: testcasesSearchSchema,
  component: TestCasesRouteComponent,
})

function TestCasesRouteComponent() {
  const { view } = Route.useParams()
  return <TestCasesPage view={view as TestCasesViewKey} />
}
