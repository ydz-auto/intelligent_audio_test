import { createFileRoute } from '@tanstack/react-router'

import Home from '@/features/home'

/**
 * / 首页门户（03_首页.md §3.1：公开路由，不进 _authenticated 组）。
 * 已登录访问仍显示门户页（站头呈登录态）；进入控制台走站头/Hero 主按钮。
 */
export const Route = createFileRoute('/')({
  component: Home,
})
