import type { HomeStatsSummary } from '@/domain/models/home'
import { toHomeStatsSummary } from '@/infrastructure/adapters/dto/home-adapter'
import type { HomeStatsSummaryDto } from '@/infrastructure/dto/home.dto'
import { request } from '@/infrastructure/api/client'

/**
 * 工作台 summary API（infrastructure 层）。
 * 接线 INT-642/INT-845：GET /api/v1/home/stats/summary（home:read 权限；
 * home_bp.py HomeStatsSummary 输出 snake_case）——snake_case→camelCase
 * 转换收敛于 adapters/dto/home-adapter（DDD 四层：domain 层不留 snake_case 穿透）。
 * INT-1032 返修：原实现直通 raw snake_case 致工作台消费端
 * （summary.recentTasks/topGroups 等 camelCase 访问）崩溃——改用 adapter 归一。
 */
export async function fetchHomeStatsSummary(): Promise<HomeStatsSummary> {
  const dto = await request<HomeStatsSummaryDto>('GET', '/home/stats/summary')
  return toHomeStatsSummary(dto)
}
