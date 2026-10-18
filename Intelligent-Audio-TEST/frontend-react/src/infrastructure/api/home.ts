/**
 * 首页统计 API（infrastructure/api 层，接线 INT-728 经统一 client.ts）。
 *   GET /api/v1/home/stats/details（home:read；home.py HomeStatsDetails）
 * 403 → application 层降级 anonymous 态（门户页容错不报错）。
 * snake_case DTO → camelCase 域模型转换收敛于 adapters/dto/home-adapter。
 */
import { apiClient } from './client'
import type { HomeStatsDetails } from '@/domain/models/home'
import { toHomeStatsDetails } from '@/infrastructure/adapters/dto/home-adapter'
import type { HomeStatsDetailsDto } from '@/infrastructure/dto/home.dto'

export async function fetchHomeStatsDetails(): Promise<HomeStatsDetails> {
  const dto = await apiClient.get<HomeStatsDetailsDto | null>(
    '/home/stats/details'
  )
  return toHomeStatsDetails(dto)
}
