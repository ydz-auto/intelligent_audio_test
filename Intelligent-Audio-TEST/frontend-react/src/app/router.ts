import { createRouter } from '@tanstack/react-router'

import { routeTree } from '../routeTree.gen'
import { ROUTE_PENDING_OPTIONS } from './router-pending'

/**
 * TanStack Router 实例（文件式路由，routeTree.gen.ts 由 router-plugin 生成）。
 *
 * INT-2392：路由级待定态。生产构建 autoCodeSplitting 把各页拆成懒加载 chunk，
 * 目标 chunk 就绪前若不配置 pendingComponent，router 不会呈现待定 lane，旧页面
 * 会一直挂着（URL 已变、界面不动）。待定组件与时长见 app/router-pending.ts；
 * defaultPreload intent 保留（hover/聚焦即预取 chunk，命中时根本不进待定态）。
 */
export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  ...ROUTE_PENDING_OPTIONS,
})


declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
