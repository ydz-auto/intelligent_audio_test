import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { requirePermission } from '@/application/auth/route-guards'
import { AiChatPage } from '@/features/ai-chat'

const aiChatSearchSchema = z.object({
  /** URL 契约：/ai-chat?report={id}（报告中心/详情入口，INT-360 声明） */
  report: z.coerce.string().optional().catch(undefined),
  /** URL 契约：/ai-chat?task={id}（任务详情入口，INT-354 声明；进入即预填指令） */
  task: z.coerce.string().optional().catch(undefined),
  /** URL 契约：/ai-chat?reviewTask={id}&reviewCase={caseId}（08 §3.7 扩展，
   * AI 复核会话「展开到 /ai-chat」进入态——把复核上下文+结论带入主会话继续追问） */
  reviewTask: z.coerce.string().optional().catch(undefined),
  reviewCase: z.coerce.string().optional().catch(undefined),
})

/**
 * /ai-chat AI 对话页（08_AI对话页.md §3.1）：
 * report:read 守卫（无权限 → /403?from）；validateSearch 携带 report/task/reviewTask/reviewCase；
 * key={report ?? task ?? reviewTask ?? ''} 换上下文即重开会话（照 playground key 语义）。
 */
export const Route = createFileRoute('/_authenticated/ai-chat')({
  validateSearch: aiChatSearchSchema,
  beforeLoad: ({ location }) => {
    requirePermission('report:read', location)
  },
  component: AiChatPageRouteComponent,
})

function AiChatPageRouteComponent() {
  const search = Route.useSearch()
  return (
    <AiChatPage
      initialContext={{
        report: search.report,
        task: search.task,
        reviewTask: search.reviewTask,
        reviewCase: search.reviewCase,
      }}
      key={search.report ?? search.task ?? search.reviewTask ?? 'empty'}
    />
  )
}
