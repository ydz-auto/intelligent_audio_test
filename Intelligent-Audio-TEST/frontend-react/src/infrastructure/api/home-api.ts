/**
 * 工作台 summary API（infrastructure/api 层，接线 INT-728 经统一 client.ts）。
 *   GET /api/v1/home/stats/summary（home:read；home.py HomeStatsSummary）
 * snake_case DTO → camelCase 域模型转换收敛于 adapters/dto/home-adapter。
 */
import { apiClient } from './client'
import type { HomeStatsSummary } from '@/domain/models/home'
import { toHomeStatsSummary } from '@/infrastructure/adapters/dto/home-adapter'
import type { HomeStatsSummaryDto } from '@/infrastructure/dto/home.dto'

export async function fetchHomeStatsSummary(): Promise<HomeStatsSummary> {
  const dto = await apiClient.get<HomeStatsSummaryDto | null>(
    '/home/stats/summary'
  )
  return toHomeStatsSummary(dto)
}
