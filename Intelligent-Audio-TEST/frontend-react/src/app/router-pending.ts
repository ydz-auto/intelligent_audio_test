/**
 * 路由级待定态配置（基座；INT-2392）。
 *
 * 单独成文件是为了可单测：`app/router.ts` 依赖构建期生成的 `routeTree.gen.ts`
 * （.gitignore 忽略、由 router-plugin 在 dev/build 时写出），单测环境里不一定
 * 存在；把待定态配置抽出来，测试可以直接锁定「默认 pending 组件与时长」不被误删。
 *
 * - defaultPendingComponent：目标路由 chunk 未就绪时渲染的加载态（见
 *   components/route-pending.tsx）；不配置时 router 根本不会呈现待定 lane。
 * - defaultPendingMs 400：正常网络下 chunk 远早于此就绪，不闪。
 * - defaultPendingMinMs 300：一旦出现至少停留 300ms，避免临界抖动。
 */
import { RoutePending } from '@/components/route-pending'

export const ROUTE_PENDING_OPTIONS = {
  defaultPendingComponent: RoutePending,
  defaultPendingMs: 400,
  defaultPendingMinMs: 300,
} as const
