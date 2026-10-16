import { createFileRoute } from '@tanstack/react-router'

import { ApiGuide } from '@/features/user-guide/api-guide'

/**
 * /user-guide-api 平台 API 手册（07_文档.md §3.2）：顶层公开路由，与 /user-guide 同壳，
 * 经页内手册切换跨路由可达（00_页面清单与RBAC划分.md §2.1 补登记）。
 */
export const Route = createFileRoute('/user-guide-api')({
  component: ApiGuide,
})
