import { createRouter } from '@tanstack/react-router'

import { routeTree } from '../routeTree.gen'

/** TanStack Router 实例（文件式路由，routeTree.gen.ts 由 router-plugin 生成） */
export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
