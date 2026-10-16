/**
 * 个人中心 mock 数据源（infrastructure 层，红线④：mock 常量，不接真实后端）。
 * 契约对位 13_个人中心.md §2.0 能力基线：
 *  - 第三方绑定列表 GET /auth/oauth/bindings → { bindings: [...] }
 *  - 我的收藏 GET /favorites → { data: { task: [ids], report: [ids], testcase: [ids] } }
 * bindings 用可变数组承载解绑演示（mock 态解绑后可刷新消失）；收藏为 per-user 常量。
 */
import type { OAuthBinding, FavoriteCounts } from '@/domain/models/profile'

/** mock：当前演示账号的第三方绑定（提供方 id 对齐 auth.ts MOCK_OAUTH_PROVIDERS） */
export const MOCK_OAUTH_BINDINGS: OAuthBinding[] = [
  {
    providerId: '1',
    providerName: 'GitHub',
    providerSlug: 'github',
    providerIcon: 'github',
    providerUserId: 'octocat-2026',
  },
]

/** mock：当前演示账号的收藏 id 清单（per-user；计数取 length） */
export const MOCK_FAVORITES: {
  task: string[]
  report: string[]
  testcase: string[]
} = {
  task: ['T-20261001', 'T-20261002'],
  report: ['R-20260930'],
  testcase: ['TC-20261005', 'TC-20261006', 'TC-20261007'],
}

/** mock：收藏计数 → 三类数值（GET /favorites → data 三数组 length 映射） */
export function getMockFavoriteCounts(): FavoriteCounts {
  return {
    task: MOCK_FAVORITES.task.length,
    report: MOCK_FAVORITES.report.length,
    testcase: MOCK_FAVORITES.testcase.length,
  }
}
