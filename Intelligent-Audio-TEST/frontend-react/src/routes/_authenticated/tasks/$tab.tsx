import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { requirePermission } from '@/application/auth/route-guards'
import {
  TASKS_TAB_REDIRECTS,
  TASKS_TAB_WHITELIST,
  type TasksTabKey,
} from '@/features/tasks/constants'
import { TasksPage } from '@/features/tasks'
import { TaskDetailRoutePage } from '@/features/tasks/detail/task-detail-route-page'

/**
 * /tasks/$tab 三页签列表 + /tasks/:id 详情（09_任务域.md §3.2 + §4.1；
 * 18_挑选合并交互重设计.md §2.2 裁定①：旧「合并」页签收编为「挑选合并」）。
 *
 * TanStack Router 同层级不允许两个 `$param` 兄弟路由（共享树节点，后注册者被前者遮蔽，
 * new-process-route-tree.js parseSegments existingNode 复用），因此详情并入本路由分支：
 *  tab ∈ 白名单 → 列表页；tab 为数字 → 详情页；'merged'（旧路径）→ redirect cherry-picks；
 *  否则重定向 daily。
 * URL 口径与规范一致：页签路径式 /tasks/$tab、详情 /tasks/:id。
 * validateSearch（zod + .catch()，URL 化可分享/回退）；task:read 守卫。
 */
const tasksSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(10),
  search: z.string().optional().catch(undefined),
  status: z.string().optional().catch(undefined),
  evaluationStatus: z.string().optional().catch(undefined),
  tag: z.string().optional().catch(undefined),
  timeRange: z.string().optional().catch(undefined),
  favorite: z.boolean().optional().catch(undefined),
  trash: z.boolean().optional().catch(undefined),
})

const NUMERIC_ID = /^\d+$/

export const Route = createFileRoute('/_authenticated/tasks/$tab')({
  beforeLoad: ({ params, location }) => {
    requirePermission('task:read', location)
    // 旧「合并」路径 redirect 到「挑选合并」（§2.2 裁定①）
    const redirectTarget = TASKS_TAB_REDIRECTS[params.tab]
    if (redirectTarget) {
      throw redirect({ to: '/tasks/$tab', params: { tab: redirectTarget } })
    }
    if (!TASKS_TAB_WHITELIST.includes(params.tab) && !NUMERIC_ID.test(params.tab)) {
      throw redirect({ to: '/tasks/$tab', params: { tab: 'daily' } })
    }
  },
  validateSearch: tasksSearchSchema,
  component: TasksTabPage,
})

function TasksTabPage() {
  const { tab } = Route.useParams()
  if (NUMERIC_ID.test(tab)) {
    return <TaskDetailRoutePage taskId={Number(tab)} />
  }
  return <TasksPage tab={tab as TasksTabKey} />
}
