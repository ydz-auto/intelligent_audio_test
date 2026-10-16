/**
 * Benchmark Adapter —— DTO(snake_case) ⇄ Domain(camelCase) 转换
 *
 * 唯一允许做键名转换的层；api 与 composables 消费 camelCase Domain 契约。
 * 字段口径：report_service benchmark_repository _row_dict（排行行）
 * 与 _mapping_to_entity（指标映射）实测序列化结果。
 */
import type {
  BenchmarkRankingRow,
  BenchmarkRankingFilters,
  BenchmarkRankingResult,
  MetricMappingInfo,
} from '../../domain/model/benchmark'
import type {
  BenchmarkSourceType,
  BenchmarkDirectionType,
  BenchmarkSubjectTypeType,
  BenchmarkCategoryType,
  DeviceTypeType,
} from '../../domain/enums'
import type {
  BenchmarkRankingRowDto,
  BenchmarkRankingListDataDto,
  BenchmarkRankingQueryDto,
  BenchmarkComputeRequestDto,
  MetricMappingDto,
  MetricMappingListDataDto,
} from '../dto/benchmarkDto'

/** DTO 排行行 → Domain 排行行 */
export function toBenchmarkRankingRow(dto: BenchmarkRankingRowDto): BenchmarkRankingRow {
  return {
    id: dto.id,
    source: dto.source as BenchmarkSourceType,
    publishedTaskId: dto.published_task_id ?? null,
    publishedTaskVersion: dto.published_task_version ?? null,
    reportId: dto.report_id ?? null,
    baselineId: dto.baseline_id ?? null,
    subjectName: dto.subject_name,
    subjectType: dto.subject_type as BenchmarkSubjectTypeType,
    deviceType: (dto.device_type ?? null) as DeviceTypeType | null,
    benchmarkSuite: dto.benchmark_suite,
    category: dto.category as BenchmarkCategoryType,
    metricCode: dto.metric_code,
    metricName: dto.metric_name,
    metricValue: dto.metric_value,
    unit: dto.unit,
    direction: dto.direction as BenchmarkDirectionType,
    rank: dto.rank,
    total: dto.total,
    percentile: dto.percentile ?? null,
    score100: dto.score100 ?? null,
    gapBest: dto.gap_best ?? null,
    gapMedian: dto.gap_median ?? null,
    deltaExternal: dto.delta_external ?? null,
    scenarioKey: dto.scenario_key,
    computedAt: dto.computed_at ?? null,
  }
}

/** DTO 排行列表信封 → Domain 排行列表信封 */
export function toBenchmarkRankingListData(dto: BenchmarkRankingListDataDto): BenchmarkRankingResult {
  return {
    items: (dto.items || []).map(toBenchmarkRankingRow),
    total: dto.total ?? 0,
    page: dto.page ?? 1,
    perPage: dto.per_page ?? 0,
    pages: dto.pages ?? 0,
  }
}

/** DTO 指标映射 → Domain */
export function toMetricMappingInfo(dto: MetricMappingDto): MetricMappingInfo {
  return {
    id: dto.id,
    dimensionName: dto.dimension_name,
    metricCode: dto.metric_code,
    metricName: dto.metric_name,
    unit: dto.unit,
    direction: dto.direction as BenchmarkDirectionType,
    scenarioTags: dto.scenario_tags || [],
    active: dto.active,
  }
}

/** DTO 指标映射列表信封 → Domain 清单（指标筛选下拉数据源） */
export function toMetricMappingListData(dto: MetricMappingListDataDto): MetricMappingInfo[] {
  return (dto.items || []).map(toMetricMappingInfo)
}

/** Domain 筛选 → DTO 查询参数（snake_case，网关 get_ranking 契约） */
export function toBenchmarkRankingQueryDto(filters: BenchmarkRankingFilters): BenchmarkRankingQueryDto {
  return {
    ...(filters.suite ? { suite: filters.suite } : {}),
    ...(filters.category ? { category: filters.category } : {}),
    ...(filters.metricCode ? { metric_code: filters.metricCode } : {}),
    ...(filters.source ? { source: filters.source } : {}),
    ...(filters.publishedTaskId != null ? { published_task_id: filters.publishedTaskId } : {}),
    ...(filters.subjectName ? { subject_name: filters.subjectName } : {}),
  }
}

/** Domain → DTO 重算请求体（全可选 = 全量重算） */
export function toBenchmarkComputeRequestDto(
  suite?: string | null,
  category?: string | null,
  source?: string | null,
): BenchmarkComputeRequestDto {
  return {
    ...(suite ? { suite } : {}),
    ...(category ? { category } : {}),
    ...(source ? { source } : {}),
  }
}
