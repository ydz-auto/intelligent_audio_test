import type { HomeStatsSummary } from '@/domain/models/home'
import { request } from '@/infrastructure/api/client'
import { toHomeStatsSummary } from '@/infrastructure/adapters/dto/home-adapter'
import type { HomeStatsSummaryDto } from '@/infrastructure/dto/home.dto'

/**
 * 工作台 summary API（infrastructure 层）。
 * 接线 INT-845：GET /api/v1/home/stats/summary（home:read 权限；
 * home_bp.py HomeStatsSummary 输出 snake_case → 经 home-adapter 收敛
 * toHomeStatsSummary 产出 camelCase 域模型（04_控制台.md §2.0 数据命名口径）。
 */
export async function fetchHomeStatsSummary(): Promise<HomeStatsSummary> {
  const dto = await request<HomeStatsSummaryDto>('GET', '/home/stats/summary')
  return toHomeStatsSummary(dto)
}
