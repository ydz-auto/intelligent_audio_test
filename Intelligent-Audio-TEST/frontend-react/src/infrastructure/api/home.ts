import type { HomeStatsDetails } from '@/domain/models/home'
import { request } from '@/infrastructure/api/client'

/**
 * 首页统计 details API（infrastructure 层）。
 * 接线 INT-642：GET /api/v1/home/stats/details（home:read 权限；
 * home_bp.py HomeStatsDetails 输出 snake_case 直通 domain/models/home.ts，
 * 03_首页.md §7 DTO 直通口径，无需转换层）。
 */
export async function fetchHomeStatsDetails(): Promise<HomeStatsDetails> {
  return request<HomeStatsDetails>('GET', '/home/stats/details')
}
