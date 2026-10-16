/**
 * Benchmark DTO→Domain 转换层（infrastructure/adapters 唯一转换层，对齐整站
 * `infrastructure/adapters/*` 约定——15_报告域 §8 同构）。interfaces 层组件
 * 只见 camelCase Domain 字段，本层是唯一知 snake_case 的地方。
 * 全量映射表见 14_benchmark排行.md §9；回归断言：interfaces 层零 snake_case。
 */
import type {
  MetricMappingInfo,
  RankingFilters,
  RankingRow,
} from '@/domain/models/benchmark'
import type {
  BenchmarkMetricMappingDto,
  BenchmarkRankingDto,
  BenchmarkSubjectDto,
} from '@/infrastructure/mock/benchmark-mock'

/** 排行行 DTO → Domain（全字段映射；baselineId 仅排障用，组件不显示） */
export function mapRankingRowDto(dto: BenchmarkRankingDto): RankingRow {
  return {
    id: dto.id,
    source: dto.source,
    category: dto.category,
    metricCode: dto.metric_code,
    metricName: dto.metric_name,
    unit: dto.unit,
    direction: dto.direction,
    rank: dto.rank,
    total: dto.total,
    percentile: dto.percentile,
    score100: dto.score100,
    subjectName: dto.subject_name,
    subjectType: dto.subject_type,
    deviceType: dto.device_type,
    benchmarkSuite: dto.benchmark_suite,
    scenarioKey: dto.scenario_key,
    metricValue: dto.metric_value,
    gapBest: dto.gap_best,
    gapMedian: dto.gap_median,
    deltaExternal: dto.delta_external,
    publishedTaskId: dto.published_task_id,
    publishedTaskVersion: dto.published_task_version,
    reportId: dto.report_id,
    baselineId: dto.baseline_id,
    computedAt: dto.computed_at,
  }
}

/** 指标映射 DTO → Domain（指标筛选下拉数据源） */
export function mapMetricMappingDto(dto: BenchmarkMetricMappingDto): MetricMappingInfo {
  return {
    id: dto.id,
    dimensionName: dto.dimension_name,
    metricCode: dto.metric_code,
    metricName: dto.metric_name,
    unit: dto.unit,
    direction: dto.direction,
    scenarioTags: dto.scenario_tags,
    active: dto.active,
  }
}

/** 主体联想 DTO → Domain（subject_name 单一字段 → string 名称清单；搜索联想数据源） */
export function mapRankingSubjectDto(dto: BenchmarkSubjectDto): string {
  return dto.subject_name
}

/**
 * 排行榜行列表 → 指标组（application/groupRankings 的分组输入已为 camelCase；
 * 本函数仅供 DTO→Domain 链路端点，保持与整站 adapter 惯例一致）。
 */
export function mapRankingRows(dtos: BenchmarkRankingDto[]): RankingRow[] {
  return dtos.map(mapRankingRowDto)
}

/** 按 RankingFilters 对 Domain 行做前置筛选（分类/测试集/来源/主体），返回 camelCase 行 */
export function filterRankingRows(
  rows: RankingRow[],
  filters: RankingFilters
): RankingRow[] {
  return rows.filter((row) => {
    if (filters.category && row.category !== filters.category) return false
    if (filters.suite && row.benchmarkSuite !== filters.suite) return false
    if (filters.metricCode && row.metricCode !== filters.metricCode) return false
    if (filters.source && row.source !== filters.source) return false
    if (filters.subjectName && !row.subjectName.includes(filters.subjectName)) {
      return false
    }
    return true
  })
}
