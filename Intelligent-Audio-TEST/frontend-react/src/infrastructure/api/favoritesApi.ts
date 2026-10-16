/**
 * 我的收藏 API 桩（infrastructure 层，红线④：mock 常量）。
 * 契约对位 13_个人中心.md §2.0（favorite_trash_bp.py:34-37 实测）：
 *  GET /favorites?entity_type= → { data: { task: [ids], report: [ids], testcase: [ids] } }，
 *  per-user、登录即可（require_auth）。
 * TODO(API 接线): 该端点接真实实现后仅替换本文件，application/features 不感知。
 */
import type { FavoriteCounts } from '@/domain/models/profile'
import { getMockFavoriteCounts } from '@/infrastructure/mock/profile-mock'

export const FAVORITES_QUERY_KEY = ['favorites'] as const

/** 我的收藏三类计数。TODO(API 接线): GET /favorites → data 三数组 length */
export async function getFavorites(): Promise<FavoriteCounts> {
  return getMockFavoriteCounts()
}
