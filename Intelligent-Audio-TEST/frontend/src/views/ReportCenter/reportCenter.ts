// -*- coding: utf-8 -*-
/**
 * 报告中心 composable（G02，INT-741）
 *
 * 页面定位：合并 HistoryReports + TestReports 的**单一管理页**（侧栏「报告中心」）。
 * 报告列表为单一视图，默认展示全部报告（不限类型，含草稿/已发布）；
 * **类型 = 筛选条件而非页面层级**（INT-439 v2.6 口径）——由 BadgeFilter 单选承担；
 * Benchmark 报告并入（report_type='benchmark'，徽标「Benchmark 报告」）。
 *
 * 实现：复用 useHistoryReports 全量管理逻辑（分页/筛选/排序/批量/收藏/回收站/对比），
 * 视图层固定「全部」Tab（无页签），并补统计徽章快速筛选 + 统计分析入口。
 */
import { useRouter } from 'vue-router'
import { useHistoryReports, REPORT_TABS } from '../HistoryReports/historyReports'

/** 统计徽章键（数据源 GET /reports/tab-counts；点击=快速筛选，非页签层级） */
export type StatBadgeKey = 'all' | 'published' | 'draft' | 'comparison'

/** 对比报告快速筛选的组合类型值（后端 type 参数逗号分隔 IN 过滤，兼容 comparison+secondary_comparison） */
const COMPARISON_TYPE_VALUE = 'comparison,secondary_comparison'

export function useReportCenter() {
  const router = useRouter()

  // 复用历史报告全量管理逻辑（默认 activeTab=ALL，即单一列表视图）
  const core = useHistoryReports()

  // ===== 统计徽章（全量计数 + 快速筛选）=====
  /** 四个徽章的计数（键 = StatBadgeKey；服务端 tab-counts，失败回退 0） */
  const statCounts = {
    get all() { return core.tabCounts.value[REPORT_TABS.ALL] ?? 0 },
    get published() { return core.tabCounts.value[REPORT_TABS.PUBLISHED] ?? 0 },
    get draft() { return core.tabCounts.value[REPORT_TABS.DRAFT] ?? 0 },
    get comparison() { return core.tabCounts.value[REPORT_TABS.COMPARISON] ?? 0 },
  }

  /** 当前筛选是否命中某统计徽章（用于高亮） */
  const isStatActive = (key: StatBadgeKey): boolean => {
    switch (key) {
      case 'all':
        return core.filters.value.reportType === 'all' && core.filters.value.reportStatus === 'all'
      case 'published':
        return core.filters.value.reportStatus === 'published'
      case 'draft':
        return core.filters.value.reportStatus === 'draft'
      case 'comparison':
        return (core.filters.value.reportType as string) === COMPARISON_TYPE_VALUE || core.filters.value.reportType === 'comparison'
      default:
        return false
    }
  }

  /** 点击统计徽章：按快速筛选口径改写筛选栏并刷新（类型=筛选条件非页签） */
  const handleStatBadgeClick = (key: StatBadgeKey) => {
    switch (key) {
      case 'all':
        core.filters.value.reportType = 'all'
        core.filters.value.reportStatus = 'all'
        break
      case 'published':
        core.filters.value.reportStatus = 'published'
        break
      case 'draft':
        core.filters.value.reportStatus = 'draft'
        break
      case 'comparison':
        core.filters.value.reportType = COMPARISON_TYPE_VALUE as any
        core.filters.value.reportStatus = 'all'
        break
    }
    core.handleFilterChange()
  }

  /** 报告类型筛选切换（BadgeFilter 单选；含对比家族组合值支持） */
  const handleReportTypeFilterChange = (value: string | number) => {
    core.filters.value.reportType = String(value) as any
    core.handleFilterChange()
  }

  /** 统计分析入口（G04）：报告中心工具栏 → /report-statistics */
  const goStatistics = () => {
    router.push('/report-statistics')
  }

  return {
    ...core,
    statCounts,
    isStatActive,
    handleStatBadgeClick,
    handleReportTypeFilterChange,
    goStatistics,
  }
}
