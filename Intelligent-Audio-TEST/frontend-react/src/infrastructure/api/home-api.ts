import type { HomeStatsSummary } from '@/domain/models/home'
import { request } from '@/infrastructure/api/client'

/**
 * 工作台 summary API（infrastructure 层）。
 * 接线 INT-642：GET /api/v1/home/stats/summary（home:read 权限；
 * home_bp.py HomeStatsSummary 输出 snake_case 直通 domain/models/stats.ts，
 * 03_首页.md §7 DTO 直通口径）。
 */
export async function fetchHomeStatsSummary(): Promise<HomeStatsSummary> {
  return request<HomeStatsSummary>('GET', '/home/stats/summary')
}
