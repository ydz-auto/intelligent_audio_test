import { createFileRoute } from '@tanstack/react-router'

import { About } from '@/features/about'

/**
 * /about 关于页（06_关于.md §3.2）：顶层公开路由，不进 _authenticated 组。
 * 五角色 + 未登录访客同一阅读版式（§3.3）；顶部导航「关于」由 useTopNavLinks 消费。
 */
export const Route = createFileRoute('/about')({
  component: About,
})
