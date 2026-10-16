/**
 * Benchmark 报告 Adapter —— DTO(snake_case) ⇄ Domain(camelCase) 转换
 *
 * 唯一允许做键名转换的层；api 与 composables 消费 camelCase Domain 契约。
 * 字段口径：report_service benchmark_repository _benchmark_report_dict / _row_dict 实测序列化结果。
 */
import type {
  BenchmarkReportRecord,
  BenchmarkReportSnapshot,
  BenchmarkReportListData,
  BenchmarkSnapshotRow,
  BenchmarkReportCreatePayload,
  BenchmarkReportListQuery,
} from '../../domain/model/benchmarkReport'
import type {
  BenchmarkReportRecordDto,
  BenchmarkReportSnapshotDto,
  BenchmarkReportListDataDto,
  BenchmarkSnapshotRowDto,
  BenchmarkReportCreateDto,
  BenchmarkReportListQueryDto,
} from '../dto/benchmarkReportDto'

/** DTO 排行快照行 → Domain 排行快照行 */
export function toBenchmarkSnapshotRow(dto: BenchmarkSnapshotRowDto): BenchmarkSnapshotRow {
  return {
    id: dto.id,
    source: dto.source,
    publishedTaskId: dto.published_task_id ?? null,
    publishedTaskVersion: dto.published_task_version ?? null,
    reportId: dto.report_id ?? null,
    baselineId: dto.baseline_id ?? null,
    subjectName: dto.subject_name,
    subjectType: dto.subject_type,
    deviceType: dto.device_type ?? null,
    benchmarkSuite: dto.benchmark_suite,
    category: dto.category,
    metricCode: dto.metric_code,
    metricName: dto.metric_name,
    metricValue: dto.metric_value,
    unit: dto.unit,
    direction: dto.direction,
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

/** DTO 排行快照 → Domain 排行快照 */
export function toBenchmarkReportSnapshot(dto: BenchmarkReportSnapshotDto): BenchmarkReportSnapshot {
  return {
    filters: {
      suite: dto.filters.suite ?? '',
      category: dto.filters.category ?? '',
      source: dto.filters.source ?? '',
    },
    counts: {
      publishedTaskCount: dto.counts.published_task_count ?? 0,
      subjectCount: dto.counts.subject_count ?? 0,
      metricCount: dto.counts.metric_count ?? 0,
      rowCount: dto.counts.row_count ?? 0,
    },
    rows: (dto.rows || []).map(toBenchmarkSnapshotRow),
  }
}

/** DTO Benchmark 报告记录 → Domain */
export function toBenchmarkReportRecord(dto: BenchmarkReportRecordDto): BenchmarkReportRecord {
  return {
    id: dto.id,
    reportId: dto.report_id,
    taskId: dto.task_id ?? null,
    suite: dto.suite ?? '',
    category: dto.category ?? '',
    source: dto.source ?? '',
    algorithmSet: dto.algorithm_set ?? '',
    publishedTaskCount: dto.published_task_count ?? 0,
    subjectCount: dto.subject_count ?? 0,
    metricCount: dto.metric_count ?? 0,
    rankingData: dto.ranking_data ? toBenchmarkReportSnapshot(dto.ranking_data) : null,
    version: dto.version ?? 1,
    publishedBy: dto.published_by ?? '',
    publishedAt: dto.published_at ?? null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

/** DTO 列表信封 → Domain 列表信封 */
export function toBenchmarkReportListData(dto: BenchmarkReportListDataDto): BenchmarkReportListData {
  return {
    items: (dto.items || []).map(toBenchmarkReportRecord),
    total: dto.total ?? 0,
    page: dto.page ?? 1,
    perPage: dto.per_page ?? 0,
    pages: dto.pages ?? 0,
  }
}

/** Domain 发布请求 → DTO 请求体（snake_case，网关 BenchmarkReportCreateRequest 契约） */
export function toBenchmarkReportCreateDto(payload: BenchmarkReportCreatePayload): BenchmarkReportCreateDto {
  return {
    ...(payload.taskId != null ? { task_id: Number(payload.taskId) } : {}),
    ...(payload.suite ? { suite: payload.suite } : {}),
    ...(payload.category ? { category: payload.category } : {}),
    ...(payload.source ? { source: payload.source } : {}),
    ...(payload.algorithmSet ? { algorithm_set: payload.algorithmSet } : {}),
    ...(payload.name ? { name: payload.name } : {}),
    ...(payload.description ? { description: payload.description } : {}),
  }
}

/** Domain 列表查询 → DTO 查询参数（snake_case，网关 list_reports 契约） */
export function toBenchmarkReportListQueryDto(query: BenchmarkReportListQuery): BenchmarkReportListQueryDto {
  return {
    ...(query.suite ? { suite: query.suite } : {}),
    ...(query.category ? { category: query.category } : {}),
    ...(query.source ? { source: query.source } : {}),
    ...(query.taskId != null ? { task_id: query.taskId } : {}),
    ...(query.page != null ? { page: query.page } : {}),
    ...(query.perPage != null ? { per_page: query.perPage } : {}),
  }
}
