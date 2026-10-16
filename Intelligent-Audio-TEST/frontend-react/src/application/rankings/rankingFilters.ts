/**
 * 排行榜 URL search ↔ 筛选状态（application 层，照 newAPI validateSearch 模式）。
 * 全部筛选写 URL search（zod validateSearch 全 optional + catch），刷新/分享可还原。
 * 额外承载页内算法还原字段 `algorithm`（14_benchmark排行.md §3.2/§4.3）。
 */
import { z } from 'zod'

import type { RankingFilters } from '@/domain/models/benchmark'
import { DEFAULT_RANKING_FILTERS } from '@/domain/models/benchmark'

/** /rankings 路由 search 校验（全 optional + catch：非法值回退默认，不抛 400） */
export const rankingSearchSchema = z.object({
  /** 类别页签：空串=全部 / asr / voice_llm / tts / translation */
  category: z.string().optional().catch(''),
  /** 测试集标识：空串=全部测试集 */
  suite: z.string().optional().catch(''),
  /** 排行指标代码：空串=全部指标 */
  metricCode: z.string().optional().catch(''),
  /** 数据来源：空串=全部 / platform_test / external_import */
  source: z.string().optional().catch(''),
  /** 主体搜索（防抖 300ms → subjectName 参数） */
  subjectName: z.string().optional().catch(''),
  /** 页内算法（URL 可还原；null/空=全部算法） */
  algorithm: z.string().optional().catch(''),
})

export type RankingSearch = z.infer<typeof rankingSearchSchema>

export const DEFAULT_RANKING_SEARCH: RankingSearch = {
  category: '',
  suite: '',
  metricCode: '',
  source: '',
  subjectName: '',
  algorithm: '',
}

/** search 字段 → RankingFilters（algorithm 为页内 store 字段，不并入排行筛选） */
export function searchToFilters(search: RankingSearch): RankingFilters {
  return {
    category: search.category ?? '',
    suite: search.suite ?? '',
    metricCode: search.metricCode ?? '',
    source: search.source ?? '',
    subjectName: search.subjectName ?? '',
  }
}

/** 任一筛选非默认时返回 true（「重置」按钮可见性判定） */
export function hasActiveFilters(filters: RankingFilters): boolean {
  return (
    filters.category !== DEFAULT_RANKING_FILTERS.category ||
    filters.suite !== DEFAULT_RANKING_FILTERS.suite ||
    filters.metricCode !== DEFAULT_RANKING_FILTERS.metricCode ||
    filters.source !== DEFAULT_RANKING_FILTERS.source ||
    filters.subjectName !== DEFAULT_RANKING_FILTERS.subjectName
  )
}
