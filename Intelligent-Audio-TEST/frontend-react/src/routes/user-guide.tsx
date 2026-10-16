import { createFileRoute } from '@tanstack/react-router'

import { UserGuide } from '@/features/user-guide'

/**
 * /user-guide 平台使用手册（07_文档.md §3.2）：顶层公开路由，不进 _authenticated 组。
 * 五角色 + 未登录访客同一阅读版式（§3.3）；顶部导航「文档」入口落位此处。
 */
export const Route = createFileRoute('/user-guide')({
  component: UserGuide,
})
