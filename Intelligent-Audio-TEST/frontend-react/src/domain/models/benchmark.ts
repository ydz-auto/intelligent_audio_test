/**
 * Benchmark 排行领域模型（domain 层，零依赖，前端只见 camelCase）。
 * 形态对照 api_gateway/schemas/benchmark.py + report_service ReadModel
 * （benchmark_models.py BenchmarkRanking 实测字段），由 infrastructure/adapters/
 * benchmarkAdapter.ts 从 snake_case DTO 唯一转换而来（14_benchmark排行.md §9）。
 */

export type BenchmarkSource = 'platform_test' | 'external_import'
export type BenchmarkCategory = 'asr' | 'voice_llm' | 'tts' | 'translation'
export type BenchmarkDirection = 'lower_is_better' | 'higher_is_better'
export type BenchmarkSubjectType = 'open_source' | 'closed_source' | 'app'
export type BenchmarkDeviceType = 'physical' | 'http_api' | 'websocket_api'

/** 榜单行（camelCase，组件规格 §4.4/§5.3 一律引用本形态） */
export interface RankingRow {
  id: number
  /** platform_test（平台实测）/ external_import（外部基线）——双轨制 */
  source: BenchmarkSource
  category: BenchmarkCategory
  metricCode: string
  metricName: string
  unit: string
  /** lower_is_better / higher_is_better */
  direction: BenchmarkDirection
  rank: number
  total: number
  percentile: number | null
  /** 归一化分 0-100，可空（单主体不归一化） */
  score100: number | null
  subjectName: string
  subjectType: BenchmarkSubjectType
  deviceType: BenchmarkDeviceType | null
  benchmarkSuite: string
  scenarioKey: string
  metricValue: number
  gapBest: number | null
  gapMedian: number | null
  /** 实测值与外部基线值的差异（双轨并存时有值） */
  deltaExternal: number | null
  publishedTaskId: number | null
  publishedTaskVersion: number | null
  reportId: number | null
  baselineId: number | null
  computedAt: string
}

/** 排行筛选条件（URL search 全 optional + catch，照 newAPI validateSearch 模式） */
export interface RankingFilters {
  /** 类别页签：全部（空串）或 asr/voice_llm/tts/translation */
  category: string
  /** 测试集标识，默认「全部测试集」（空串） */
  suite: string
  /** 排行指标代码，默认「全部指标」（空串） */
  metricCode: string
  /** 数据来源：全部来源（空串）/ platform_test / external_import */
  source: string
  /** 主体搜索（防抖 300ms → subjectName 参数） */
  subjectName: string
}

export const DEFAULT_RANKING_FILTERS: RankingFilters = {
  category: '',
  suite: '',
  metricCode: '',
  source: '',
  subjectName: '',
}

/** 指标映射（GET /metric-mappings?activeOnly=true 形态，dimensionName 为系统维度名） */
export interface MetricMappingInfo {
  id: number
  dimensionName: string
  metricCode: string
  metricName: string
  unit: string
  direction: BenchmarkDirection
  scenarioTags: string[]
  active: boolean
}

/** 指标组（(metricCode × scenarioKey) 分组，category 由页签锁定；组内 rank 升序） */
export interface RankingGroup {
  metricCode: string
  metricName: string
  unit: string
  direction: BenchmarkDirection
  category: BenchmarkCategory
  scenarioKey: string
  /** 参与对比的模型数（组内 rows 的 total 共享值） */
  total: number
  /** 组内行（rank 升序） */
  rows: RankingRow[]
  computedAt: string
}

/** 报告详情 Benchmark 排行区块（15_报告域.md §3.8；后端 `GET /benchmarks/reports/{id}` 待接线） */
export type BenchmarkReportSourceFilter = 'measured' | 'imported' | 'all' | 'diff'

/** 排行区块行（camelCase；后端 ReadModel 待立项，桩形态由 benchmarkApi 留桩） */
export interface BenchmarkReportRankingRow {
  rank: number
  subjectName: string
  subjectType: string
  source: 'measured' | 'imported'
  metricValue: number
  gapBest: number
  percentile: number
  delta: number | null
}

/** 排行区块数据（版本标注/计算时间/中位数/最佳参考线 + 排行行） */
export interface BenchmarkReportRanking {
  version: string
  computedAt: string
  metricName: string
  unit: string
  median: number
  best: number
  rows: BenchmarkReportRankingRow[]
}
