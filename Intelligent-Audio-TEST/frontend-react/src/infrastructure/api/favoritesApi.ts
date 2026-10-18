/**
 * 我的收藏 API（infrastructure/api 层；INT-733 收藏计数 mock → 真实接口）。
 * 契约对位 13_个人中心.md §2.0（favorite_trash_bp.py:34-37 实测）：
 *  GET /favorites?entity_type= → { data: { task: [ids], report: [ids], testcase: [ids] } }，
 *  per-user、登录即可（require_auth）；entity_type 空 = 返回全部三类 id 数组。
 * 计数取各数组 length；前端只消费 camelCase 领域对象（FavoriteCounts）。
 */
import type { FavoriteCounts } from '@/domain/models/profile'
import { apiClient } from '@/infrastructure/api/client'

export const FAVORITES_QUERY_KEY = ['favorites'] as const

/** GET /favorites 原始契约（data 三数组；null 兜底防御后端缺字段） */
interface FavoritesDto {
  task?: string[] | null
  report?: string[] | null
  testcase?: string[] | null
}

/** 我的收藏三类计数：GET /favorites → data 三数组 length 映射（空/缺字段 → 0） */
export async function getFavorites(): Promise<FavoriteCounts> {
  const dto = await apiClient.get<FavoritesDto>('/favorites')
  return {
    task: dto.task?.length ?? 0,
    report: dto.report?.length ?? 0,
    testcase: dto.testcase?.length ?? 0,
  }
}
