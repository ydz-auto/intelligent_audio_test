import type { HomeStatsSummary } from '@/domain/models/stats'

import { MOCK_HOME_STATS_SUMMARY } from '../mock/dashboard-mock'

/**
 * 工作台 summary API 桩（infrastructure 层，INT-378 新增）。
 * 基座 infrastructure/api/home.ts 已覆盖 details——details 一律从基座桩取，本文件勿重复。
 * TODO(API 接线): GET /api/v1/home/stats/summary（home:read 权限，home.py HomeStatsSummary）。
 */
export async function fetchHomeStatsSummary(): Promise<HomeStatsSummary> {
  return MOCK_HOME_STATS_SUMMARY
}
