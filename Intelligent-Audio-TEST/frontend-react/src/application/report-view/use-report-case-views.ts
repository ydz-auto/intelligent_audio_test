/**
 * 具体用例三视图聚合编排（application 层，15_报告域.md §3.3.7，INT-1738）。
 *
 * 输入 = `searchCases` 全量结果行（一行 = 用例 × 资源）；
 * 输出 = 按 `test_case_id` 合并后的用例集 + 设备视图 / 结果类型视图的第 1 层节点 + 叶表可用的
 * 指标键 / 轮次 / 资源 / 结果类型集合。全部 `useMemo` 纯计算，不发额外请求。
 *
 * 三视图计数口径（§3.3.7 定死）：
 * - 用例视图 Badge = **结果行数**（接口 `total`，同一用例在多台设备上各计一行）；
 * - 设备视图 / 结果类型视图 Badge = **去重用例数**；组 / 节点计数一律去重用例数。
 */
import { useMemo } from 'react'

import type { ReportCaseItem, ReportResourceHeader } from '@/domain/models/report'

import {
  collectBaseDimensions,
  collectMetricKeys,
  collectRounds,
  DEFAULT_RESULT_TYPE,
  groupCasesByResource,
  groupCasesByResultType,
  mergeCaseRowsByCaseId,
  type MergedReportCase,
  type ResourceNode,
  type ResultTypeNode,
} from './report-case-view-model'

/** 聚合上限（§3.3.7 降级提示文案：聚合仅覆盖前 10000 条） */
export const REPORT_CASE_AGGREGATE_LIMIT = 10000

export interface ReportCaseViews {
  /** 按 test_case_id 合并后的用例（保持服务端顺序） */
  mergedCases: MergedReportCase[]
  /** 去重用例数 */
  caseCount: number
  /** 设备视图第 1 层节点 */
  resourceNodes: ResourceNode[]
  /** 结果类型视图第 1 层节点 */
  resultTypeNodes: ResultTypeNode[]
  /** 是否渲染「结果类型视图」档（至少 1 个非「默认」结果类型） */
  hasResultTypeView: boolean
  /** 全部指标键（未去轮次后缀） */
  metricKeys: string[]
  /** 基础维度名（去轮次后缀） */
  baseDimensions: string[]
  /** 数据中出现的轮次标记（overall / round:N） */
  rounds: string[]
  /** 数据中出现的资源键 */
  resourceKeys: string[]
  /** 数据中出现的 result_type */
  resultTypes: string[]
}

/**
 * 三视图聚合（纯计算）。
 * @param rows 结果行（全量，一行 = 用例 × 资源）
 * @param headers `summary.resource_headers`（资源显示名 / 类型 / result_type 解析）
 */
export function useReportCaseViews(
  rows: ReportCaseItem[],
  headers: ReportResourceHeader[] = []
): ReportCaseViews {
  return useMemo(() => {
    const mergedCases = mergeCaseRowsByCaseId(rows)
    const resourceNodes = groupCasesByResource(mergedCases, headers)
    const resultTypeNodes = groupCasesByResultType(mergedCases, headers)
    const metricKeys = collectMetricKeys(mergedCases)
    const resourceKeys = resourceNodes.map((n) => n.key)
    const resultTypes = resultTypeNodes.map((n) => n.key)
    return {
      mergedCases,
      caseCount: mergedCases.length,
      resourceNodes,
      resultTypeNodes,
      hasResultTypeView: resultTypes.some((t) => t !== DEFAULT_RESULT_TYPE),
      metricKeys,
      baseDimensions: collectBaseDimensions(metricKeys),
      rounds: collectRounds(metricKeys),
      resourceKeys,
      resultTypes,
    }
  }, [rows, headers])
}
