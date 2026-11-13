import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/application/auth/route-guards'
import { AgentProvidersPage } from '@/features/agent-providers'
import { AGENT_PROVIDER_MANAGE_PERMISSION } from '@/features/agent-providers/constants'

/**
 * /agent-providers 模型供应商管理（INT-2493 / §6.4 / §11）。
 * 登录壳 _authenticated 组内页面；权限码 agent:provider:manage（INT-2488 网关同码），
 * 侧栏入口与路由守卫同一权限集合：无权限时入口不渲染，URL 直达被守卫拦截到 /403。
 */
export const Route = createFileRoute('/_authenticated/agent-providers')({
  beforeLoad: ({ location }) => {
    requirePermission(AGENT_PROVIDER_MANAGE_PERMISSION, location)
  },
  component: AgentProvidersPage,
})
