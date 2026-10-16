/**
 * Benchmark 排行领域模型 —— camelCase Domain 契约
 *
 * 唯一做 snake_case⇄camelCase 键名转换的层是 infrastructure/adapters；
 * views / composables / store 只允许消费本文件的 camelCase 类型。
 * 字段口径对应功能设计文档《报告Benchmark排行功能设计文档.md》§6.3
 * 与 report_service/infrastructure/persistence/models/benchmark_models.py 实测。
 */
import type {
  BenchmarkSourceType,
  BenchmarkDirectionType,
  BenchmarkSubjectTypeType,
  BenchmarkCategoryType,
  DeviceTypeType,
} from '../enums'

/** 排行查询筛选（camelCase Domain；转查询参数时经 benchmarkAdapter） */
export interface BenchmarkRankingFilters {
  suite?: string | null
  category?: string | null
  metricCode?: string | null
  source?: BenchmarkSourceType | null
  subjectName?: string | null
  publishedTaskId?: number | null
}

/** Benchmark 排行行（ReadModel 行，双轨：platform_test / external_import） */
export interface BenchmarkRankingRow {
  id: number
  source: BenchmarkSourceType
  publishedTaskId: number | null
  publishedTaskVersion: number | null
  reportId: number | null
  baselineId: number | null
  subjectName: string
  subjectType: BenchmarkSubjectTypeType
  deviceType: DeviceTypeType | null
  benchmarkSuite: string
  category: BenchmarkCategoryType
  metricCode: string
  metricName: string
  metricValue: number
  unit: string
  direction: BenchmarkDirectionType
  rank: number
  total: number
  percentile: number | null
  score100: number | null
  gapBest: number | null
  gapMedian: number | null
  deltaExternal: number | null
  scenarioKey: string
  computedAt: string | null
}

/** 排行列表信封（INT-297：单页全量，无分页语义） */
export interface BenchmarkRankingResult {
  items: BenchmarkRankingRow[]
  total: number
  page: number
  perPage: number
  pages: number
}

/** 指标映射信息（指标筛选下拉数据源） */
export interface MetricMappingInfo {
  id: number
  dimensionName: string
  metricCode: string
  metricName: string
  unit: string
  direction: BenchmarkDirectionType
  scenarioTags: string[]
  active: boolean
}

/** 排行分组（category×metric×scenario 一组，组内按 rank 升序） */
export interface BenchmarkRankingGroup {
  category: BenchmarkCategoryType
  metricCode: string
  metricName: string
  scenarioKey: string
  unit: string
  direction: BenchmarkDirectionType
  computedAt: string | null
  total: number
  rows: BenchmarkRankingRow[]
}
