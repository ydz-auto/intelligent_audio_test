/**
 * 报告列表查询装配（application 层；INT-596 P2-5 返修）。
 * interfaces 层不直 import infrastructure/adapters（P2-20 范式：经 application 层再导出，依赖单向），
 * 且算法类型以 camelCase 入参——interfaces 层零 snake_case 构造。
 * 原 reports/index.tsx、reports-showcase/index.tsx 直连 adapter 并在特性层写 `algorithm_type` 键，
 * 现收敛本层：URL 搜索态 + 生效算法类型 → ReportListQuery DTO（infrastructure 唯一知 snake_case）。
 */
import type { ReportListQuery } from '@/domain/models/report'
import type { ReportsSearch, ShowcaseSearch } from '@/domain/models/report-search'
import {
  buildReportListQuery as buildReportListQueryDto,
  buildShowcaseQuery as buildShowcaseQueryDto,
} from '@/infrastructure/adapters/reportAdapter'

export type { ReportListQuery }

/**
 * 报告中心：URL 搜索态 + 生效算法类型（camelCase）→ 列表查询 DTO。
 * algorithmType 已含全局算法/URL 显式值/'none' 解除语义，undefined = 不按算法过滤。
 */
export function buildReportListQuery(
  search: ReportsSearch,
  algorithmType?: string
): ReportListQuery {
  return { ...buildReportListQueryDto(search), algorithm_type: algorithmType }
}

/** 展示页：URL 搜索态 + 生效算法类型（camelCase）→ 列表查询 DTO（展示页固定 status='published' 由 usePublishedReportList 注入） */
export function buildShowcaseQuery(
  search: ShowcaseSearch,
  algorithmType?: string
): ReportListQuery {
  return { ...buildShowcaseQueryDto(search), algorithm_type: algorithmType }
}
