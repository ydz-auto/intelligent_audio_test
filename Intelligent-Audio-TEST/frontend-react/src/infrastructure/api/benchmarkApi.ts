/**
 * Benchmark 排行 HTTP 客户端（infrastructure 层，唯一知 snake_case 的层之一）。
 * 接线 INT-642：统一经基座 client.ts（INT-605）访问真实后端端点（benchmark_bp.py），
 * 不再返回 mock 常量。DTO→Domain 转换由 adapters/benchmarkAdapter.ts 唯一承担
 * （14_benchmark排行.md §9）；client 信封解包后本层只透出 INT-297 单页全量列表 data。
 *
 * 端点契约（查询参数原样透传；client 自动剔除 undefined/null）：
 *   GET  /api/v1/benchmarks/ranking        ?suite=&category=&metricCode=&source=&publishedTaskId=
 *   GET  /api/v1/benchmarks/ranking/subjects ?suite=
 *   GET  /api/v1/benchmarks/metric-mappings  ?activeOnly=
 *   POST /api/v1/benchmarks/ranking/compute （Body: { suite?, category?, source? }）
 *
 * 说明：subjectName 不在发给后端的查询参数内——后端为精确匹配，而主体搜索是
 * 联想输入（防抖 300ms 写 URL，未选中前是局部串），精确匹配会打空列表；主体
 * 子串筛选由 application 层 filterRankingRows 在 Domain 行上承担（与 mock 阶段同口径）。
 */
import type { BenchmarkMetricMappingDto, BenchmarkRankingDto } from '@/infrastructure/api/benchmarkTypes'
import { request } from '@/infrastructure/api/client'

export interface RankingQueryParams {
  suite?: string
  category?: string
  metricCode?: string
  source?: string
  publishedTaskId?: number | null
}

/** INT-297 列表信封的 data 段（后端单页全量：page=1, pages=1） */
export interface BenchmarkListData<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GET /api/v1/benchmarks/ranking（排行主查询；query 透传后端精确筛选） */
export async function fetchBenchmarkRanking(
  params: RankingQueryParams
): Promise<BenchmarkListData<BenchmarkRankingDto>> {
  return request<BenchmarkListData<BenchmarkRankingDto>>(
    'GET',
    '/benchmarks/ranking',
    undefined,
    {
      // 内联对象字面量以匹配 ApiRequestOptions.params: Record<string, unknown>
      // （undefined/null 由 client 剔除）
      params: {
        suite: params.suite,
        category: params.category,
        metricCode: params.metricCode,
        source: params.source,
        publishedTaskId: params.publishedTaskId,
      },
      // INT-1225：/rankings 为公开路由，匿名/会话失效 401 不触发 sessionExpired
      // 整页跳登录——由页面按 14_benchmark排行.md §5.1 权限空态/错误态降级。
      skipAuthRedirect: true,
    }
  )
}

/** GET /api/v1/benchmarks/ranking/subjects（参与排行的被测主体去重清单；后端返回纯字符串数组） */
export async function fetchBenchmarkRankingSubjects(
  suite?: string
): Promise<BenchmarkListData<string>> {
  return request<BenchmarkListData<string>>(
    'GET',
    '/benchmarks/ranking/subjects',
    undefined,
    { params: { suite }, skipAuthRedirect: true }
  )
}

/** GET /api/v1/benchmarks/metric-mappings?activeOnly=true（指标筛选下拉数据源） */
export async function fetchBenchmarkMetricMappings(
  activeOnly = true
): Promise<BenchmarkListData<BenchmarkMetricMappingDto>> {
  return request<BenchmarkListData<BenchmarkMetricMappingDto>>(
    'GET',
    '/benchmarks/metric-mappings',
    undefined,
    { params: { activeOnly }, skipAuthRedirect: true }
  )
}

/**
 * POST /api/v1/benchmarks/ranking/compute（全量重算排行）。
 * 业务失败由 client 抛 ApiError（httpStatus=400 + 中文 message），调用方 mutation 兜住；
 * 成功仅需确认不抛错（返回 data 段，前端不消费）。
 */
export async function computeBenchmarkRanking(params: {
  suite?: string
  category?: string
  source?: string
}): Promise<void> {
  await request('POST', '/benchmarks/ranking/compute', params)
}

// ---------------------------------------------------------------------------
// 报告详情 Benchmark 排行区块（15_报告域.md §3.8）
// 后端暂无 `GET /benchmarks/reports/{reportId}` 端点（实测 404）→ 本层留桩 // 待接线，
// 桩返回符合后端 ReadModel 形态的示例（与报告发布 POST /benchmarks/reports 属同一 benchmark_bp）。
// FEAT 卡：报告排行端点立项（GET /benchmarks/reports/{reportId}）。
// ---------------------------------------------------------------------------

/** 报告详情排行 DTO（桩形态；report_id + 版本/计算时间/中位数/最佳 + 排行行） */
export interface BenchmarkReportRankingDto {
  report_id: number
  version: string
  computed_at: string
  metric_name: string
  unit: string
  median: number
  best: number
  rows: BenchmarkReportRankingRowDto[]
}

/** 排行区块行 DTO（source: measured/imported 双轨，delta 双轨并存时非空） */
export interface BenchmarkReportRankingRowDto {
  rank: number
  subject_name: string
  subject_type: string
  source: 'measured' | 'imported'
  metric_value: number
  gap_best: number
  percentile: number
  delta: number | null
}

/** 桩示例数据（与 FEAT 立项后端 ReadModel 对齐；接真实端点后本函数改为 request 调用） */
const MOCK_REPORT_RANKING: Omit<BenchmarkReportRankingDto, 'report_id'> = {
  version: 'v20261016.1',
  computed_at: '2026-10-16T09:30:00',
  metric_name: '唤醒成功率',
  unit: '%',
  median: 93.2,
  best: 97.8,
  rows: [
    { rank: 1, subject_name: '旗舰-01（平台实测）', subject_type: '设备', source: 'measured', metric_value: 97.8, gap_best: 0, percentile: 100, delta: 1.2 },
    { rank: 2, subject_name: 'asr-streaming-v3', subject_type: '商业 API', source: 'measured', metric_value: 96.4, gap_best: -1.4, percentile: 92, delta: null },
    { rank: 3, subject_name: '开源基线 whisper-large', subject_type: '开源模型', source: 'imported', metric_value: 95.1, gap_best: -2.7, percentile: 81, delta: 0.8 },
    { rank: 4, subject_name: '旗舰-02（平台实测）', subject_type: '设备', source: 'measured', metric_value: 94.3, gap_best: -3.5, percentile: 70, delta: -0.4 },
    { rank: 5, subject_name: 'wakeword-detect-v2', subject_type: '商业 API', source: 'measured', metric_value: 93.2, gap_best: -4.6, percentile: 58, delta: null },
    { rank: 6, subject_name: '友商 A 音箱', subject_type: '已上线 APP', source: 'imported', metric_value: 90.6, gap_best: -7.2, percentile: 37, delta: 2.1 },
    { rank: 7, subject_name: '入门-03（平台实测）', subject_type: '设备', source: 'measured', metric_value: 89.4, gap_best: -8.4, percentile: 25, delta: -1.6 },
  ],
}

/** 报告详情排行（待接线：GET /api/v1/benchmarks/reports/{reportId}；桩返回示例） */
export async function fetchBenchmarkReportRanking(
  reportId: number
): Promise<BenchmarkReportRankingDto> {
  // 待接线：真实端点立项后改为
  //   return request<BenchmarkReportRankingDto>('GET', `/benchmarks/reports/${reportId}`)
  void reportId
  return { report_id: reportId, ...MOCK_REPORT_RANKING }
}
