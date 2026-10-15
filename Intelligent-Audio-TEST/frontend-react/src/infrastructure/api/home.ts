import type { HomeStatsDetails } from '@/domain/models/home'

/**
 * 首页统计 API 桩（红线④：mock 常量）。
 * TODO(API 接线): GET /api/v1/home/stats/details（home:read 权限；
 * 403 → application 层降级 anonymous 态，门户页容错不报错）。
 */

/** mock 数字（形态对照 HomeStatsDetails schema；演示口径非真实数据） */
export const MOCK_HOME_STATS: HomeStatsDetails = {
  test_cases: { total: 128, groups: 12 },
  tasks: { total: 342, completed: 297, running: 3, failed: 42 },
  devices: { online: 8, offline: 2, total: 10 },
  audio_files: { total: 1560, dry: 980, noise: 320, prompt: 260 },
  playback_devices: 6,
  apis: { online: 4, offline: 1, total: 5 },
  reports: 289,
  dimensions: { total: 18, with_endpoints: 9, endpoints: 24 },
  updated_at: null,
}

export async function fetchHomeStatsDetails(): Promise<HomeStatsDetails> {
  return MOCK_HOME_STATS
}
