import { createFileRoute } from '@tanstack/react-router'

import { AgentProvidersPage } from '@/features/agent-providers'

/**
 * /agent-providers 模型供应商管理（INT-2493 / §6.4 / §11）。
 * 供应商按用户隔离（owner_id），每个登录用户都配置并使用自己的模型 Key，
 * 因此不再要求 ``agent:provider:manage`` 权限码；仅需登录。
 */
export const Route = createFileRoute('/_authenticated/agent-providers')({
  component: AgentProvidersPage,
})
