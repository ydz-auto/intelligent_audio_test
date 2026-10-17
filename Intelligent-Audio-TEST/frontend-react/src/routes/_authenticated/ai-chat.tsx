import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { AiChatPage } from '@/features/ai-chat'

const aiChatSearchSchema = z.object({
  /** URL 契约：/ai-chat?report={id}（报告中心/详情入口，INT-360 声明） */
  report: z.coerce.string().optional().catch(undefined),
  /** URL 契约：/ai-chat?task={id}（任务详情入口，INT-354 声明；进入即预填指令） */
  task: z.coerce.string().optional().catch(undefined),
})

/**
 * /ai-chat AI 对话页（08_AI对话页.md §3.1）：
 * report:read 守卫（无权限 → /403?from=/ai-chat）；validateSearch 携带 report/task；
 * key={report ?? ''} 换报告上下文即重开会话（照 playground key 语义）。
 */
export const Route = createFileRoute('/_authenticated/ai-chat')({
  validateSearch: aiChatSearchSchema,
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'report:read')) {
      throw redirect({ to: '/403', search: { from: '/ai-chat' } })
    }
  },
  component: AiChatPageRouteComponent,
})

function AiChatPageRouteComponent() {
  const search = Route.useSearch()
  return (
    <AiChatPage
      initialContext={{ report: search.report, task: search.task }}
      key={search.report ?? search.task ?? 'empty'}
    />
  )
}
