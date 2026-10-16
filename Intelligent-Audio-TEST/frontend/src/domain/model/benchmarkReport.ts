/**
 * Benchmark 报告领域模型 —— camelCase Domain 契约（INT-483 报告发布接线）
 *
 * 唯一做 snake_case⇄camelCase 键名转换的层是 infrastructure/adapters；
 * views / composables / store 只允许消费本文件的 camelCase 类型。
 * 字段口径对应 report_service/infrastructure/persistence/benchmark_repository.py
 * _benchmark_report_dict / _row_dict（INT-481 第五表 benchmark_reports 实测序列化结果）。
 *
 * 注意：本文件自含 Benchmark 排行「数据来源/排行方向」枚举与标签（值 = 后端契约原值），
 * 与 INT-482 排行页在 domain/enums.ts 定义的 BenchmarkSource/BenchmarkDirection 值一致但独立成源，
 * 避免跨分支合并时同文件重复声明冲突；两端联调后如需收敛可再统一。
 */

/** Benchmark 报告数据来源（值 = 后端 RankingSource 契约原值，禁止改动值） */
export const BenchmarkReportSource = {
  PLATFORM_TEST: 'platform_test',
  EXTERNAL_IMPORT: 'external_import',
} as const

/** Benchmark 报告数据来源类型（由 BenchmarkReportSource 派生的字符串联合） */
export type BenchmarkReportSourceType = typeof BenchmarkReportSource[keyof typeof BenchmarkReportSource]

/** Benchmark 报告数据来源标签（展示用，与枚举值一一对应） */
export const BenchmarkReportSourceLabels: Record<BenchmarkReportSourceType, string> = {
  [BenchmarkReportSource.PLATFORM_TEST]: '平台实测',
  [BenchmarkReportSource.EXTERNAL_IMPORT]: '外部基线',
}

/** Benchmark 排行方向（值 = 后端 RankingDirection 契约原值，禁止改动值） */
export const BenchmarkReportDirection = {
  LOWER_IS_BETTER: 'lower_is_better',
  HIGHER_IS_BETTER: 'higher_is_better',
} as const

/** Benchmark 排行方向类型 */
export type BenchmarkReportDirectionType = typeof BenchmarkReportDirection[keyof typeof BenchmarkReportDirection]

/** Benchmark 排行方向标签（展示用） */
export const BenchmarkReportDirectionLabels: Record<BenchmarkReportDirectionType, string> = {
  [BenchmarkReportDirection.LOWER_IS_BETTER]: '越低越好',
  [BenchmarkReportDirection.HIGHER_IS_BETTER]: '越高越好',
}

/** 排行快照行（发布时点定格；与 INT-482 BenchmarkRankingRow 同构，独立成源避免跨分支依赖） */
export interface BenchmarkSnapshotRow {
  id: number
  source: BenchmarkReportSourceType | (string & {})
  publishedTaskId: number | null
  publishedTaskVersion: number | null
  reportId: number | null
  baselineId: number | null
  subjectName: string
  subjectType: string
  deviceType: string | null
  benchmarkSuite: string
  category: string
  metricCode: string
  metricName: string
  metricValue: number
  unit: string
  direction: BenchmarkReportDirectionType | (string & {})
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

/** 排行快照（发布时点定格，报告不随后续重算漂移） */
export interface BenchmarkReportSnapshot {
  filters: {
    suite: string
    category: string
    source: string
  }
  counts: {
    publishedTaskCount: number
    subjectCount: number
    metricCount: number
    rowCount: number
  }
  rows: BenchmarkSnapshotRow[]
}

/** Benchmark 报告发布记录（benchmark_reports 行 → camelCase） */
export interface BenchmarkReportRecord {
  id: number
  reportId: number
  taskId?: number | null
  suite: string
  category: string
  source: string
  algorithmSet: string
  publishedTaskCount: number
  subjectCount: number
  metricCount: number
  /** 列表接口不携带大体积排行快照（详情接口再取），缺省为 null */
  rankingData?: BenchmarkReportSnapshot | null
  version: number
  publishedBy: string
  publishedAt?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

/** Benchmark 报告列表信封（/benchmarks/reports GET 契约） */
export interface BenchmarkReportListData {
  items: BenchmarkReportRecord[]
  total: number
  page: number
  perPage: number
  pages: number
}

/** Benchmark 报告列表查询（camelCase；adapter 转 snake_case 查询参数） */
export interface BenchmarkReportListQuery {
  suite?: string
  category?: string
  source?: string
  taskId?: number
  page?: number
  perPage?: number
}

/** 发布 Benchmark 报告请求（camelCase；全字段可选 = 聚合当前全量排行快照） */
export interface BenchmarkReportCreatePayload {
  taskId?: number | null
  suite?: string
  category?: string
  source?: string
  algorithmSet?: string
  name?: string
  description?: string
}
