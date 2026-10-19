import type { HomeStatsDetails } from '@/domain/models/home'
import { request } from '@/infrastructure/api/client'
import { toHomeStatsDetails } from '@/infrastructure/adapters/dto/home-adapter'
import type { HomeStatsDetailsDto } from '@/infrastructure/dto/home.dto'

/**
 * 首页统计 details API（infrastructure 层）。
 * 接线 INT-845：GET /api/v1/home/stats/details（home:read 权限；
 * home_bp.py HomeStatsDetails 输出 snake_case → 经 home-adapter 收敛
 * toHomeStatsDetails 产出 camelCase 域模型（04_控制台.md §2.0 数据命名口径）。
 */
export async function fetchHomeStatsDetails(): Promise<HomeStatsDetails> {
  const dto = await request<HomeStatsDetailsDto>('GET', '/home/stats/details')
  return toHomeStatsDetails(dto)
}
