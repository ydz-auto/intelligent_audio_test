import { createFileRoute } from '@tanstack/react-router'

import { rankingSearchSchema } from '@/application/rankings/rankingFilters'
import { RankingsPage } from '@/features/rankings'

/**
 * /rankings 排行榜公开路由（14_benchmark排行.md §9）：
 * 不进 _authenticated 组（URL 直达可达、数据 403 空态不跳登录——INT-344 口径）；
 * validateSearch(zod) 校验筛选，**不设权限硬守卫**；AUTH_MODE=off（现状部署）全员放行。
 */
export const Route = createFileRoute('/rankings')({
  validateSearch: rankingSearchSchema,
  component: RankingsPage,
})
