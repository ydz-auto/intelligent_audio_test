/**
 * 我的收藏 API（infrastructure/api 层；接线 INT-650 切真实接口）。
 * 契约对位 13_个人中心.md §2.0（favorite_trash_bp.py:34-37 实测）：
 *  GET /favorites → data: { task: [ids], report: [ids], testcase: [ids] }，
 *  per-user、登录即可（require_auth）。
 */
import type { FavoriteCounts } from '@/domain/models/profile'
import { request } from '@/infrastructure/api/client'
import type { FavoriteIdsDto } from '@/infrastructure/dto/profile.dto'
import { toFavoriteCounts } from '@/infrastructure/dto/profile.dto'

export const FAVORITES_QUERY_KEY = ['favorites'] as const

/** 我的收藏三类计数（GET /favorites → data 三数组 length） */
export async function getFavorites(): Promise<FavoriteCounts> {
  const dto = await request<FavoriteIdsDto>('GET', '/favorites')
  return toFavoriteCounts(dto ?? { task: [], report: [], testcase: [] })
}
