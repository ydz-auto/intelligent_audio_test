import { createFileRoute } from '@tanstack/react-router'

import { IntegrationGuide } from '@/features/user-guide/integration-guide'

/**
 * /user-guide-integration 平台接入指南（07_文档.md §3.2 同壳）：顶层公开路由，
 * 与 /user-guide 同壳，经页内手册切换跨路由可达（接入方开发者：Realtime/HTTP/设备三章）。
 */
export const Route = createFileRoute('/user-guide-integration')({
  component: IntegrationGuide,
})
