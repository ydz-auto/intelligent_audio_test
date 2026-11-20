import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { AgentSkillsPage } from '@/features/agent-skills'
import { AGENT_SKILL_MANAGE_PERMISSION } from '@/features/agent-skills/constants'

/**
 * /agent-skills Skill 管理（INT-2550 / 方案 §4.4 / §11）。
 *
 * 登录壳 _authenticated 组内页面；权限码 agent:skill:manage（INT-2549 网关
 * 同码），侧栏入口与路由守卫同一权限集合：无权限时入口不渲染，URL 直达被
 * 守卫拦截到 /403?from=/agent-skills。
 *
 * 可选 query：`?name=&description=` 供「沉淀为 Skill」建议直达新建草稿并预填。
 */
export const Route = createFileRoute('/_authenticated/agent-skills')({
  validateSearch: (search: Record<string, unknown>): AgentSkillsSearch => ({
    name: typeof search.name === 'string' ? search.name : undefined,
    description:
      typeof search.description === 'string' ? search.description : undefined,
  }),
  beforeLoad: ({ location }) => {
    requirePermission(AGENT_SKILL_MANAGE_PERMISSION, location)
  },
  component: AgentSkillsRoute,
})

type AgentSkillsSearch = {
  name?: string
  description?: string
}

function AgentSkillsRoute() {
  const { name, description } = Route.useSearch()
  const prefill = name || description ? { name, description } : null
  return <AgentSkillsPage prefill={prefill} />
}
