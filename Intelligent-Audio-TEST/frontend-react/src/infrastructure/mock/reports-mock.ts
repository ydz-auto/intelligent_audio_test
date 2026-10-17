/**
 * 报告域 mock 常量（红线④：数据一律 mock，不接真实后端）。
 * 字段形态对照 api_gateway/schemas/report.py 实测 schema + INT-439 报告域 v2.2 层级
 * （见 domain/models/report.ts 与 doc/UX设计规范/15_报告域.md §1），数字口径与基座
 * 工作台 mock（任务 342/已完成 297、设备 8 在线/2 离线）互不打架。
 * 列表与详情 id 联动：1201=任务报告、1190=对比报告、1188=二次对比报告，供详情页跳转核对。
 */
import type {
  ReportApiInfo,
  ReportApiStat,
  ReportCaseCategory,
  ReportCaseItem,
  ReportCaseListData,
  ReportComparisonTable,
  ReportCounts,
  ReportDetailData,
  ReportDeviceInfo,
  ReportDeviceStat,
  ReportListItem,
  ReportMetricConfig,
  ReportRawDataGroup,
  ReportSummary,
  ReportTag,
  ReportTagMetricGroup,
} from '@/domain/models/report'

/** GET /reports 列表 mock（分页在 useReportList 中按 per_page 截断模拟） */
export const MOCK_REPORT_LIST_ITEMS: ReportListItem[] = [
  {
    id: 1201,
    name: '旗舰音箱全量回归 · 第 3 轮报告',
    type: 'task',
    task_id: 1042,
    task_name: '智能音箱旗舰机型全量回归 · 第 3 轮',
    algorithm_type: 'asr_streaming',
    summary: { total_cases: 48, completed_cases: 48, failed_cases: 3, pass_rate: 93.8 },
    description: '旗舰音箱第 3 轮全量回归：48 条用例覆盖唤醒、识别与误触场景。',
    status: 'published',
    is_favorite: true,
    created_at: '2026-10-15T09:20:00',
    updated_at: '2026-10-15T09:20:00',
  },
  {
    id: 1200,
    name: '车载语音助手唤醒词响应报告',
    type: 'task',
    task_id: 1041,
    task_name: '车载语音助手唤醒词响应测试',
    algorithm_type: 'wakeword_detect',
    summary: { total_cases: 96, completed_cases: 96, failed_cases: 4, pass_rate: 95.8 },
    description: '车载场景唤醒词响应：近场/远场/噪声三组对比。',
    status: 'published',
    is_favorite: false,
    created_at: '2026-10-14T18:12:00',
    updated_at: '2026-10-14T18:12:00',
  },
  {
    id: 1199,
    name: 'API 通道并发稳定性验证报告',
    type: 'task',
    task_id: 1040,
    task_name: 'API 通道并发稳定性验证（压测时段）',
    algorithm_type: 'asr_streaming',
    summary: { total_cases: 60, completed_cases: 37, failed_cases: 23, pass_rate: 61.7 },
    description: '压测时段 API 通道稳定性：并发 32 路，部分接口超时。',
    status: 'draft',
    is_favorite: false,
    created_at: '2026-10-14T15:40:00',
  },
  {
    id: 1198,
    name: '耳机产品线夜间批量回归报告',
    type: 'task',
    task_id: 1039,
    task_name: '耳机产品线夜间批量回归',
    algorithm_type: 'tts_eval',
    summary: { total_cases: 120, completed_cases: 120, failed_cases: 5, pass_rate: 95.8 },
    description: '耳机产品线 120 条用例夜间批量回归，主链路全部通过。',
    status: 'published',
    is_favorite: true,
    created_at: '2026-10-14T09:10:00',
    updated_at: '2026-10-14T09:11:00',
  },
  {
    id: 1197,
    name: '多方言识别准确性抽样报告',
    type: 'task',
    task_id: 1037,
    task_name: '多方言识别准确性抽样测试',
    algorithm_type: 'asr_streaming',
    summary: { total_cases: 72, completed_cases: 72, failed_cases: 11, pass_rate: 84.7 },
    description: '粤语/四川话/东北话抽样识别准确性。',
    status: 'published',
    is_favorite: false,
    created_at: '2026-10-13T12:05:00',
    updated_at: '2026-10-13T12:06:00',
  },
  {
    id: 1196,
    name: 'TTS 自然度主观评估报告（第 2 期）',
    type: 'task',
    task_id: 1036,
    task_name: 'TTS 自然度主观评估（第 2 期）',
    algorithm_type: 'tts_eval',
    summary: { total_cases: 54, completed_cases: 20, failed_cases: 0, pass_rate: 0 },
    description: '主观评估第 2 期：因人工打分未完成，通过率暂缺。',
    status: 'draft',
    is_favorite: false,
    created_at: '2026-10-12T16:30:00',
  },
  {
    id: 1195,
    name: 'Q3 音箱品类回归汇总报告（合并 4 任务）',
    type: 'task',
    task_id: 1035,
    task_name: 'Q3 音箱品类回归汇总（合并自 4 个任务）',
    algorithm_type: 'asr_streaming',
    summary: { total_cases: 384, completed_cases: 384, failed_cases: 12, pass_rate: 96.9 },
    description: 'Q3 音箱品类汇总：合并 4 个任务的 384 条用例。',
    status: 'published',
    is_favorite: false,
    created_at: '2026-10-11T10:20:00',
    updated_at: '2026-10-11T10:21:00',
  },
  {
    id: 1190,
    name: '旗舰音箱 vs 车载助手 唤醒性能对比报告',
    type: 'comparison',
    task_id: undefined,
    task_name: '4 个任务对比',
    algorithm_type: 'wakeword_detect',
    summary: { total_cases: 0, completed_cases: 0, failed_cases: 0, pass_rate: 0, task_count: 4 },
    description: '对比任务 1041/1037/1035/1042 的唤醒性能与识别准确率差异。',
    status: 'published',
    is_favorite: true,
    created_at: '2026-10-15T10:02:00',
    updated_at: '2026-10-15T10:02:00',
  },
  {
    id: 1188,
    name: '二次对比：方言识别 × 噪声场景',
    type: 'secondary_comparison',
    task_id: undefined,
    task_name: '3 个报告对比',
    algorithm_type: 'asr_streaming',
    summary: { total_cases: 0, completed_cases: 0, failed_cases: 0, pass_rate: 0, task_count: 3 },
    description: '基于报告 1197/1200/1201 的二次对比：噪声场景下的识别差异。',
    status: 'published',
    is_favorite: false,
    created_at: '2026-10-15T11:30:00',
    updated_at: '2026-10-15T11:30:00',
  },
  {
    id: 1186,
    name: '耳机唤醒词误触率评估（草稿）',
    type: 'comparison',
    task_id: undefined,
    task_name: '2 个任务对比',
    algorithm_type: 'wakeword_detect',
    summary: { total_cases: 0, completed_cases: 0, failed_cases: 0, pass_rate: 0, task_count: 2 },
    status: 'draft',
    is_favorite: false,
    created_at: '2026-10-10T14:45:00',
  },
  // 回收站（deleted=true，favorite/trash 工具条核对用）
  {
    id: 1180,
    name: '旧版音箱回归报告（已废弃）',
    type: 'task',
    task_id: 1021,
    task_name: '音箱第 2 轮回归',
    algorithm_type: 'asr_streaming',
    summary: { total_cases: 42, completed_cases: 40, failed_cases: 2, pass_rate: 95.2 },
    status: 'draft',
    is_favorite: false,
    deleted: true,
    deleted_at: '2026-10-08T09:00:00',
    created_at: '2026-10-02T11:00:00',
  },
  {
    id: 1179,
    name: 'TTS 自然度主观评估报告（第 1 期）',
    type: 'task',
    task_id: 1015,
    task_name: 'TTS 自然度主观评估（第 1 期）',
    algorithm_type: 'tts_eval',
    summary: { total_cases: 60, completed_cases: 60, failed_cases: 3, pass_rate: 95.0 },
    status: 'published',
    is_favorite: false,
    deleted: true,
    deleted_at: '2026-10-07T16:20:00',
    created_at: '2026-09-28T09:30:00',
  },
  // Benchmark 报告（INT-500 v2.9：report_type='benchmark'，列表并入报告中心类型筛选、详情复用 /report/$reportId）
  {
    id: 1185,
    name: '唤醒性能 Benchmark 排行报告（2026-10）',
    type: 'benchmark',
    task_id: undefined,
    task_name: '多友商横向能力对比',
    algorithm_type: 'wakeword_detect',
    summary: { total_cases: 96, completed_cases: 96, failed_cases: 4, pass_rate: 95.8, task_count: 6 },
    description: '多厂商模型/APP/API 在同一标准化环境、同一测试集与指标下同时实测，按指标与场景生成名次。',
    status: 'published',
    is_favorite: true,
    created_at: '2026-10-16T09:30:00',
    updated_at: '2026-10-16T09:31:00',
  },
] satisfies ReportListItem[]

/**
 * 高级搜索元信息（任务类型/设备类型/创建者；报告中心筛选 §2 实测 :186-188）。
 * mock 确定性映射——列表项不带这些字段时按 id 合并；filter 可走查、接线后由后端查询参数承载。
 */
export const MOCK_REPORT_ADVANCED_META: Record<
  number,
  { task_type: string; device_type: string; creator: string }
> = {
  1201: { task_type: 'e2e', device_type: 'smart_speaker', creator: 'demo_admin' },
  1200: { task_type: 'e2e', device_type: 'car_voice', creator: 'demo_admin' },
  1199: { task_type: 'api', device_type: 'smart_speaker', creator: 'algo_engineer' },
  1198: { task_type: 'e2e', device_type: 'headphone', creator: 'demo_admin' },
  1197: { task_type: 'api', device_type: 'smart_speaker', creator: 'demo_admin' },
  1196: { task_type: 'api', device_type: 'smart_speaker', creator: 'algo_engineer' },
  1195: { task_type: 'mixed', device_type: 'smart_speaker', creator: 'demo_admin' },
  1190: { task_type: 'mixed', device_type: 'smart_speaker', creator: 'algo_engineer' },
  1188: { task_type: 'mixed', device_type: 'smart_speaker', creator: 'algo_engineer' },
  1186: { task_type: 'mixed', device_type: 'headphone', creator: 'demo_admin' },
  1180: { task_type: 'e2e', device_type: 'smart_speaker', creator: 'demo_admin' },
  1179: { task_type: 'api', device_type: 'smart_speaker', creator: 'algo_engineer' },
  1185: { task_type: 'benchmark', device_type: 'mixed', creator: 'algo_engineer' },
}

/** GET /reports/counts（全量非回收站项分类计数；口径修正 2026-10-16 取消页签后仍作筛选 chips/徽章行计数源） */
export const MOCK_REPORT_COUNTS: ReportCounts = {
  all: 11,
  draft: 3,
  published: 8,
  // P3-1 口径对齐：comparison 只计 type='comparison'（2 项：1190/1186），不含二次对比——
  // 与类型 chips 同源（对比2+二次1）、与快速筛选 type='comparison' 的实选结果一致
  comparison: 2,
  // benchmark 分项（1185 已发布；徽章行 4 枚固定，类型 chips 已含 Benchmark 计数）
  benchmark: 1,
}

/** 报告头算法徽标色板数据源（算法枚举，对照 api_gateway/schemas/algorithm.py 实测名） */
export const REPORT_ALGORITHMS = [
  'asr_streaming',
  'asr_offline',
  'wakeword_detect',
  'tts_eval',
  'spl_eval',
  'voice_llm',
] as const

/** 生成报告 Dialog 任务选择器（GET /tasks 只读子集：已完成任务） */
export const MOCK_COMPLETED_TASKS = [
  { id: 1041, name: '车载语音助手唤醒词响应测试', type: 'e2e', status: 'completed', completed_at: '2026-10-14T17:05:00' },
  { id: 1037, name: '多方言识别准确性抽样测试', type: 'api', status: 'completed', completed_at: '2026-10-13T11:02:00' },
  { id: 1035, name: 'Q3 音箱品类回归汇总（合并自 4 个任务）', type: 'mixed', status: 'completed', completed_at: '2026-10-11T10:00:00' },
  { id: 1015, name: 'TTS 自然度主观评估（第 1 期）', type: 'api', status: 'completed', completed_at: '2026-09-28T09:30:00' },
] as const

// ---------------------------------------------------------------------------
// 算法定义 mock（INT-436/INT-442「当前算法」大卡：GET /algorithm/definitions 形态）
// ---------------------------------------------------------------------------

export interface MockAlgorithmDefinition {
  type: string
  name: string
  group_name?: string
  category?: string
  description: string
  status?: string
  icon?: string
}

/** GET /algorithm/definitions（algorithm:read；AlgorithmDefinitionDto 形态） */
export const MOCK_ALGORITHM_DEFINITIONS: MockAlgorithmDefinition[] = [
  {
    type: 'asr-v3',
    name: '通用识别引擎',
    group_name: '语音识别',
    category: 'asr',
    description: '端到端语音识别基线模型，覆盖远场/近场/噪声三类场景。',
    status: 'online',
    icon: 'audio-waveform',
  },
  {
    type: 'asr-stream',
    name: '流式识别引擎',
    group_name: '语音识别',
    category: 'asr',
    description: '低延迟流式转写引擎，适合实时字幕与对话场景。',
    status: 'online',
    icon: 'activity',
  },
  {
    type: 'eval-ensemble',
    name: '多维评估集成',
    group_name: '评估算法',
    category: 'eval',
    description: '多维度指标集成评估算法，输出 WER/LLM 评分/延迟等综合结论。',
    status: 'online',
    icon: 'gauge',
  },
]

/** GET /algorithm/options（algorithm:read；AlgorithmOptionDto 形态——仅在线算法） */
export const MOCK_ALGORITHM_OPTIONS = MOCK_ALGORITHM_DEFINITIONS.map((a) => ({
  value: a.type,
  name: a.name,
  group_name: a.group_name,
  icon: a.icon,
}))

// ---------------------------------------------------------------------------
// 报告详情 mock（INT-439 v2.2 层级：任务级 TaskReportPanel + 对比家族）
// ---------------------------------------------------------------------------

/** 报告详情 mock 源（key=报告 id；消费方按 id 取，缺省回退 1201） */
export const MOCK_REPORT_DETAILS: Record<number, ReportDetailData> = {
  1201: buildTaskReportDetail(),
  1190: buildComparisonReportDetail('comparison'),
  1188: buildComparisonReportDetail('secondary_comparison'),
  1185: buildBenchmarkReportDetail(),
}

/**
 * 任意列表 id → 详情 mock（INT-503 补齐：列表全部 ID 可点开，杜绝「报告不存在」）。
 * 1201/1190/1188/1185 走富详情；其余按列表项参数化生成等价形态（任务级 / 对比家族 / Benchmark）。
 */
export function getReportDetailMock(reportId: number): ReportDetailData | undefined {
  const fixed = MOCK_REPORT_DETAILS[reportId]
  if (fixed) return fixed
  const item = MOCK_REPORT_LIST_ITEMS.find((i) => i.id === reportId)
  if (!item) return undefined
  if (item.type === 'benchmark') return buildBenchmarkReportDetailFor(item)
  if (item.type === 'task') return buildTaskReportDetailFor(item)
  return buildComparisonReportDetailFor(item)
}

/** 由列表项生成任务级报告详情（共享 buildTaskSummary 的指标/用例/设备数据，头部与计数按列表项覆盖） */
function buildTaskReportDetailFor(item: ReportListItem): ReportDetailData {
  const summary = buildTaskSummary({
    total_cases: item.summary.total_cases,
    completed_cases: item.summary.completed_cases,
    failed_cases: item.summary.failed_cases,
  })
  return {
    id: item.id,
    name: item.name,
    type: 'task',
    task_id: item.task_id,
    task_type: 'e2e',
    task_name: item.task_name,
    algorithm_type: item.algorithm_type,
    description: item.description,
    status: item.status,
    analysis:
      `「${item.name}」共执行 ${item.summary.total_cases} 条用例，完成 ${item.summary.completed_cases} 条、失败 ${item.summary.failed_cases} 条，整体通过率 ${item.summary.pass_rate}%。\n` +
      'asr-streaming-v3 与 wakeword-detect-v2 双算法对比：流式识别平均响应 385ms，优于唤醒检测链路；入门机型识别准确率较旗舰低约 2.4 个百分点，属预期硬件差异。',
    summary,
    created_at: item.created_at,
    updated_at: item.updated_at ?? item.created_at,
  }
}

/** 由列表项生成对比/二次对比报告详情（复用对比家族 summary 装配，头部按列表项覆盖） */
function buildComparisonReportDetailFor(item: ReportListItem): ReportDetailData {
  const base = buildComparisonReportDetail(
    item.type === 'secondary_comparison' ? 'secondary_comparison' : 'comparison'
  )
  const count = item.summary.task_count ?? (item.type === 'secondary_comparison' ? 3 : 2)
  return {
    ...base,
    id: item.id,
    name: item.name,
    type: item.type,
    task_id: undefined,
    task_type: undefined,
    task_name: `${count} 个任务对比`,
    algorithm_type: item.algorithm_type,
    description: item.description,
    status: item.status,
    summary: { ...base.summary, task_count: count, total_cases: item.summary.total_cases },
    created_at: item.created_at,
    updated_at: item.updated_at ?? item.created_at,
  }
}

/** Benchmark 报告详情（§3.8：报告头操作组 + 任务级分区复用 + 内嵌「Benchmark 排行」区块；summary 走任务级形态） */
function buildBenchmarkReportDetail(): ReportDetailData {
  const summary = buildTaskSummary()
  summary.total_cases = 96
  summary.completed_cases = 96
  summary.failed_cases = 4
  summary.resource_headers = summary.resource_headers.map((h) => ({
    ...h,
    label: h.label.replace('智能音箱-', '被测-'),
  }))
  summary.resources = ['device_1', 'device_2', 'device_3', 'api_101', 'api_102']
  return {
    id: 1185,
    name: '唤醒性能 Benchmark 排行报告（2026-10）',
    type: 'benchmark',
    task_id: undefined,
    task_type: 'benchmark',
    task_name: '多友商横向能力对比',
    algorithm_type: 'wakeword_detect',
    description: '多厂商模型/APP/API 在同一标准化环境、同一测试集与指标下同时实测，按指标与场景生成名次。',
    status: 'published',
    analysis:
      '多友商横向能力对比：6 个被测主体在统一唤醒测试集与评估指标下同时实测，整体通过率 95.8%。' +
      '旗舰系列与开源基线差距最小（gap -1.2%），闭源商业 API 平均响应最短；第三方 APP 端因系统裁剪差异存在 ±0.5% 抖动。',
    summary,
    created_at: '2026-10-16T09:30:00',
    updated_at: '2026-10-16T09:31:00',
  }
}

/** 由列表项生成 Benchmark 报告详情（头部按列表项覆盖，summary 复用富详情任务级形态） */
function buildBenchmarkReportDetailFor(item: ReportListItem): ReportDetailData {
  const base = buildBenchmarkReportDetail()
  return {
    ...base,
    id: item.id,
    name: item.name,
    description: item.description,
    status: item.status,
    summary: {
      ...base.summary,
      total_cases: item.summary.total_cases,
      completed_cases: item.summary.completed_cases,
      failed_cases: item.summary.failed_cases,
      task_count: item.summary.task_count,
    },
    created_at: item.created_at,
    updated_at: item.updated_at ?? item.created_at,
  }
}

function buildTaskSummary(overrides?: {
  total_cases?: number
  completed_cases?: number
  failed_cases?: number
}): ReportSummary {
  const allMetrics: ReportMetricConfig[] = [
    { id: 101, name: '唤醒成功率', unit: '%', decimal_places: 1, dimension_type: 'main' },
    { id: 102, name: '误唤醒率', unit: '%', decimal_places: 1, dimension_type: 'sub', parent_dimension_id: 101, parent_dimension_name: '唤醒成功率' },
    { id: 103, name: '识别准确率', unit: '%', decimal_places: 1, dimension_type: 'main' },
    { id: 104, name: '平均WER', unit: '%', decimal_places: 2, dimension_type: 'sub', parent_dimension_id: 103, parent_dimension_name: '识别准确率' },
    { id: 105, name: '平均响应时间', unit: 'ms', decimal_places: 0, dimension_type: 'main' },
  ]

  const deviceStats: ReportDeviceStat[] = [
    {
      id: 1, name: '智能音箱-旗舰-01', model: 'Xiaomi Speaker Pro', type: 'smart_speaker',
      system: 'MIUI Home', system_version: '3.2.1', status: 'online',
      total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8,
      metrics: { 唤醒成功率: 96.5, 识别准确率: 94.2, 平均响应时间: 412 },
    },
    {
      id: 2, name: '智能音箱-旗舰-02', model: 'Xiaomi Speaker Pro', type: 'smart_speaker',
      system: 'MIUI Home', system_version: '3.2.1', status: 'offline',
      total_cases: 24, completed_cases: 24, failed_cases: 1, success_rate: 95.8,
      metrics: { 唤醒成功率: 95.4, 识别准确率: 93.1, 平均响应时间: 428 },
    },
    {
      id: 3, name: '智能音箱-入门-03', model: 'Xiaomi Speaker Lite', type: 'smart_speaker',
      system: 'MIUI Home', system_version: '2.9.0', status: 'online',
      total_cases: 24, completed_cases: 24, failed_cases: 2, success_rate: 91.7,
      metrics: { 唤醒成功率: 93.1, 识别准确率: 91.8, 平均响应时间: 486 },
    },
  ]

  const apiStats: ReportApiStat[] = [
    {
      id: 101, name: 'asr-streaming-v3', status: 'active', max_process: 32, health_score: 0.92,
      total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8,
      avg_response_time: 385, stability: 0.98, metrics: { 平均响应时间: 385, 稳定性: 0.98 },
    },
    {
      id: 102, name: 'wakeword-detect-v2', status: 'active', max_process: 16, health_score: 0.88,
      total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8,
      avg_response_time: 201, stability: 0.99, metrics: { 平均响应时间: 201, 稳定性: 0.99 },
    },
  ]

  const resourceHeaders = [
    { key: 'device_1', label: '智能音箱-旗舰-01', type: 'device', id: 1, name: '智能音箱-旗舰-01' },
    { key: 'device_1_realtime', label: '智能音箱-旗舰-01 · 实时', type: 'device', id: 1, name: '智能音箱-旗舰-01', result_type: 'realtime' },
    { key: 'device_1_final', label: '智能音箱-旗舰-01 · 最终', type: 'device', id: 1, name: '智能音箱-旗舰-01', result_type: 'final' },
    { key: 'device_2', label: '智能音箱-旗舰-02', type: 'device', id: 2, name: '智能音箱-旗舰-02' },
    { key: 'device_3', label: '智能音箱-入门-03', type: 'device', id: 3, name: '智能音箱-入门-03' },
    { key: 'api_101', label: 'asr-streaming-v3', type: 'api', id: 101, name: 'asr-streaming-v3' },
    { key: 'api_101_realtime', label: 'asr-streaming-v3 · 实时', type: 'api', id: 101, name: 'asr-streaming-v3', result_type: 'realtime' },
    { key: 'api_101_final', label: 'asr-streaming-v3 · 最终', type: 'api', id: 101, name: 'asr-streaming-v3', result_type: 'final' },
    { key: 'api_102', label: 'wakeword-detect-v2', type: 'api', id: 102, name: 'wakeword-detect-v2' },
  ]

  const rawData: ReportRawDataGroup[] = [
    {
      resource: 'device_1',
      metrics: [
        { metric: '唤醒成功率', values: [100, 96.5, 93.2, 100, 88.5, 97.8, 92.4, 95.1, 100, 91.2] },
        { metric: '识别准确率', values: [96.8, 93.4, 90.1, 95.6, 88.2, 94.7, 92.3, 97.2, 90.8, 93.9] },
        { metric: '平均响应时间', values: [405, 412, 430, 398, 452, 421, 409, 416, 445, 402] },
      ],
    },
    {
      resource: 'device_1_realtime',
      metrics: [
        { metric: '唤醒成功率', values: [98.5, 95.1, 92.0, 98.0, 87.9, 96.4, 91.6, 94.0, 98.2, 90.4] },
        { metric: '识别准确率', values: [95.2, 92.6, 89.4, 94.0, 87.5, 93.2, 91.4, 95.8, 90.0, 92.6] },
        { metric: '平均响应时间', values: [412, 419, 436, 405, 458, 428, 416, 424, 452, 409] },
      ],
    },
    {
      resource: 'device_1_final',
      metrics: [
        { metric: '唤醒成功率', values: [100, 97.2, 94.0, 100, 89.1, 98.4, 93.1, 95.8, 100, 92.0] },
        { metric: '识别准确率', values: [97.4, 94.0, 90.8, 96.2, 88.9, 95.6, 93.1, 98.0, 91.6, 94.6] },
        { metric: '平均响应时间', values: [400, 406, 425, 394, 447, 415, 404, 410, 439, 397] },
      ],
    },
    {
      resource: 'device_2',
      metrics: [
        { metric: '唤醒成功率', values: [95.4, 92.8, 97.1, 94.5, 90.6, 96.2, 93.8, 98.0, 91.9, 95.7] },
        { metric: '识别准确率', values: [93.1, 91.4, 95.2, 92.8, 88.6, 94.1, 91.5, 96.0, 90.2, 93.7] },
        { metric: '平均响应时间', values: [428, 415, 439, 421, 456, 430, 422, 418, 441, 425] },
      ],
    },
    {
      resource: 'device_3',
      metrics: [
        { metric: '唤醒成功率', values: [91.2, 94.8, 88.9, 93.5, 90.1, 95.2, 89.8, 92.6, 94.3, 90.9] },
        { metric: '识别准确率', values: [91.8, 90.2, 93.5, 89.7, 92.4, 88.9, 94.1, 90.6, 92.8, 91.4] },
        { metric: '平均响应时间', values: [486, 470, 502, 478, 495, 481, 510, 469, 488, 479] },
      ],
    },
    {
      resource: 'api_101',
      metrics: [
        { metric: '唤醒成功率', values: [96.0, 94.8, 97.2, 95.5, 93.1, 96.8, 94.2, 97.9, 95.0, 96.4] },
        { metric: '识别准确率', values: [94.5, 92.8, 95.6, 93.4, 90.8, 94.9, 92.1, 96.2, 93.5, 94.7] },
        { metric: '平均响应时间', values: [385, 392, 378, 401, 396, 382, 390, 375, 398, 386] },
      ],
    },
    {
      resource: 'api_101_realtime',
      metrics: [
        { metric: '唤醒成功率', values: [95.4, 94.1, 96.4, 94.8, 92.5, 96.0, 93.6, 97.0, 94.3, 95.6] },
        { metric: '识别准确率', values: [93.9, 92.1, 94.9, 92.7, 90.2, 94.2, 91.5, 95.5, 92.9, 94.0] },
        { metric: '平均响应时间', values: [392, 400, 385, 408, 403, 389, 397, 382, 405, 393] },
      ],
    },
    {
      resource: 'api_101_final',
      metrics: [
        { metric: '唤醒成功率', values: [96.6, 95.4, 97.8, 96.1, 93.8, 97.4, 94.8, 98.6, 95.7, 97.0] },
        { metric: '识别准确率', values: [95.1, 93.4, 96.2, 94.0, 91.4, 95.5, 92.7, 96.8, 94.1, 95.3] },
        { metric: '平均响应时间', values: [378, 384, 371, 394, 389, 375, 383, 368, 391, 379] },
      ],
    },
    {
      resource: 'api_102',
      metrics: [
        { metric: '唤醒成功率', values: [95.2, 93.8, 96.4, 94.1, 91.6, 95.8, 93.2, 97.0, 94.4, 95.6] },
        { metric: '识别准确率', values: [92.7, 90.4, 94.1, 91.8, 88.9, 93.2, 90.6, 95.0, 91.4, 93.8] },
        { metric: '平均响应时间', values: [201, 208, 195, 212, 198, 204, 210, 192, 206, 199] },
      ],
    },
  ]

  const metricData = [
    {
      resource: 'device_1',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 96.5 },
        { id: 102, metric: '误唤醒率', value: 3.5 },
        { id: 103, metric: '识别准确率', value: 94.2 },
        { id: 104, metric: '平均WER', value: 5.8 },
        { id: 105, metric: '平均响应时间', value: 412 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.0 }, { id: 102, metric: '误唤醒率', value: 3.1 }, { id: 103, metric: '识别准确率', value: 94.7 }, { id: 104, metric: '平均WER', value: 5.5 }, { id: 105, metric: '平均响应时间', value: 400 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.5 }, { id: 102, metric: '误唤醒率', value: 6.1 }, { id: 103, metric: '识别准确率', value: 89.2 }, { id: 104, metric: '平均WER', value: 8.2 }, { id: 105, metric: '平均响应时间', value: 478 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.3 }, { id: 102, metric: '误唤醒率', value: 4.0 }, { id: 103, metric: '识别准确率', value: 91.8 }, { id: 104, metric: '平均WER', value: 7.1 }, { id: 105, metric: '平均响应时间', value: 437 }] },
      ],
    },
    {
      resource: 'device_1_realtime',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 96.2 },
        { id: 102, metric: '误唤醒率', value: 3.8 },
        { id: 103, metric: '识别准确率', value: 93.8 },
        { id: 104, metric: '平均WER', value: 6.2 },
        { id: 105, metric: '平均响应时间', value: 418 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.7 }, { id: 102, metric: '误唤醒率', value: 3.4 }, { id: 103, metric: '识别准确率', value: 94.3 }, { id: 104, metric: '平均WER', value: 5.9 }, { id: 105, metric: '平均响应时间', value: 406 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.2 }, { id: 102, metric: '误唤醒率', value: 6.4 }, { id: 103, metric: '识别准确率', value: 88.8 }, { id: 104, metric: '平均WER', value: 8.6 }, { id: 105, metric: '平均响应时间', value: 485 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.0 }, { id: 102, metric: '误唤醒率', value: 4.3 }, { id: 103, metric: '识别准确率', value: 91.4 }, { id: 104, metric: '平均WER', value: 7.5 }, { id: 105, metric: '平均响应时间', value: 443 }] },
      ],
    },
    {
      resource: 'device_1_final',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 96.8 },
        { id: 102, metric: '误唤醒率', value: 3.2 },
        { id: 103, metric: '识别准确率', value: 94.6 },
        { id: 104, metric: '平均WER', value: 5.4 },
        { id: 105, metric: '平均响应时间', value: 405 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.3 }, { id: 102, metric: '误唤醒率', value: 2.8 }, { id: 103, metric: '识别准确率', value: 95.1 }, { id: 104, metric: '平均WER', value: 5.1 }, { id: 105, metric: '平均响应时间', value: 393 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.8 }, { id: 102, metric: '误唤醒率', value: 5.8 }, { id: 103, metric: '识别准确率', value: 89.6 }, { id: 104, metric: '平均WER', value: 7.8 }, { id: 105, metric: '平均响应时间', value: 470 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.6 }, { id: 102, metric: '误唤醒率', value: 3.7 }, { id: 103, metric: '识别准确率', value: 92.2 }, { id: 104, metric: '平均WER', value: 6.7 }, { id: 105, metric: '平均响应时间', value: 429 }] },
      ],
    },
    {
      resource: 'device_2',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 95.4 },
        { id: 102, metric: '误唤醒率', value: 4.1 },
        { id: 103, metric: '识别准确率', value: 93.1 },
        { id: 104, metric: '平均WER', value: 6.9 },
        { id: 105, metric: '平均响应时间', value: 428 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.9 }, { id: 102, metric: '误唤醒率', value: 3.7 }, { id: 103, metric: '识别准确率', value: 93.6 }, { id: 104, metric: '平均WER', value: 6.6 }, { id: 105, metric: '平均响应时间', value: 415 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.4 }, { id: 102, metric: '误唤醒率', value: 6.7 }, { id: 103, metric: '识别准确率', value: 88.1 }, { id: 104, metric: '平均WER', value: 9.3 }, { id: 105, metric: '平均响应时间', value: 496 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.2 }, { id: 102, metric: '误唤醒率', value: 4.6 }, { id: 103, metric: '识别准确率', value: 90.7 }, { id: 104, metric: '平均WER', value: 8.2 }, { id: 105, metric: '平均响应时间', value: 454 }] },
      ],
    },
    {
      resource: 'device_3',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 93.1 },
        { id: 102, metric: '误唤醒率', value: 5.2 },
        { id: 103, metric: '识别准确率', value: 91.8 },
        { id: 104, metric: '平均WER', value: 8.2 },
        { id: 105, metric: '平均响应时间', value: 486 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.6 }, { id: 102, metric: '误唤醒率', value: 4.8 }, { id: 103, metric: '识别准确率', value: 92.3 }, { id: 104, metric: '平均WER', value: 7.9 }, { id: 105, metric: '平均响应时间', value: 471 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 86.1 }, { id: 102, metric: '误唤醒率', value: 7.8 }, { id: 103, metric: '识别准确率', value: 86.8 }, { id: 104, metric: '平均WER', value: 10.6 }, { id: 105, metric: '平均响应时间', value: 564 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 91.9 }, { id: 102, metric: '误唤醒率', value: 5.7 }, { id: 103, metric: '识别准确率', value: 89.4 }, { id: 104, metric: '平均WER', value: 9.5 }, { id: 105, metric: '平均响应时间', value: 515 }] },
      ],
    },
    {
      resource: 'api_101',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 96.0 },
        { id: 102, metric: '误唤醒率', value: 3.9 },
        { id: 103, metric: '识别准确率', value: 94.5 },
        { id: 104, metric: '平均WER', value: 5.5 },
        { id: 105, metric: '平均响应时间', value: 385 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.5 }, { id: 102, metric: '误唤醒率', value: 3.5 }, { id: 103, metric: '识别准确率', value: 95.0 }, { id: 104, metric: '平均WER', value: 5.2 }, { id: 105, metric: '平均响应时间', value: 373 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.0 }, { id: 102, metric: '误唤醒率', value: 6.5 }, { id: 103, metric: '识别准确率', value: 89.5 }, { id: 104, metric: '平均WER', value: 7.9 }, { id: 105, metric: '平均响应时间', value: 447 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.8 }, { id: 102, metric: '误唤醒率', value: 4.4 }, { id: 103, metric: '识别准确率', value: 92.1 }, { id: 104, metric: '平均WER', value: 6.8 }, { id: 105, metric: '平均响应时间', value: 408 }] },
      ],
    },
    {
      resource: 'api_101_realtime',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 95.6 },
        { id: 102, metric: '误唤醒率', value: 4.2 },
        { id: 103, metric: '识别准确率', value: 94.1 },
        { id: 104, metric: '平均WER', value: 5.9 },
        { id: 105, metric: '平均响应时间', value: 392 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.1 }, { id: 102, metric: '误唤醒率', value: 3.8 }, { id: 103, metric: '识别准确率', value: 94.6 }, { id: 104, metric: '平均WER', value: 5.6 }, { id: 105, metric: '平均响应时间', value: 380 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.6 }, { id: 102, metric: '误唤醒率', value: 6.8 }, { id: 103, metric: '识别准确率', value: 89.1 }, { id: 104, metric: '平均WER', value: 8.3 }, { id: 105, metric: '平均响应时间', value: 455 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.4 }, { id: 102, metric: '误唤醒率', value: 4.7 }, { id: 103, metric: '识别准确率', value: 91.7 }, { id: 104, metric: '平均WER', value: 7.2 }, { id: 105, metric: '平均响应时间', value: 416 }] },
      ],
    },
    {
      resource: 'api_101_final',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 96.4 },
        { id: 102, metric: '误唤醒率', value: 3.6 },
        { id: 103, metric: '识别准确率', value: 94.8 },
        { id: 104, metric: '平均WER', value: 5.1 },
        { id: 105, metric: '平均响应时间', value: 378 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.9 }, { id: 102, metric: '误唤醒率', value: 3.2 }, { id: 103, metric: '识别准确率', value: 95.3 }, { id: 104, metric: '平均WER', value: 4.8 }, { id: 105, metric: '平均响应时间', value: 367 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.4 }, { id: 102, metric: '误唤醒率', value: 6.2 }, { id: 103, metric: '识别准确率', value: 89.8 }, { id: 104, metric: '平均WER', value: 7.5 }, { id: 105, metric: '平均响应时间', value: 438 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.2 }, { id: 102, metric: '误唤醒率', value: 4.1 }, { id: 103, metric: '识别准确率', value: 92.4 }, { id: 104, metric: '平均WER', value: 6.4 }, { id: 105, metric: '平均响应时间', value: 401 }] },
      ],
    },
    {
      resource: 'api_102',
      metrics: [
        { id: 101, metric: '唤醒成功率', value: 95.2 },
        { id: 102, metric: '误唤醒率', value: 4.6 },
        { id: 103, metric: '识别准确率', value: 92.7 },
        { id: 104, metric: '平均WER', value: 7.3 },
        { id: 105, metric: '平均响应时间', value: 201 },
      ],
      categories: [
        { categoryId: 'grp-wakeup', categoryName: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.7 }, { id: 102, metric: '误唤醒率', value: 4.2 }, { id: 103, metric: '识别准确率', value: 93.2 }, { id: 104, metric: '平均WER', value: 7.0 }, { id: 105, metric: '平均响应时间', value: 195 }] },
        { categoryId: 'grp-noise', categoryName: '噪声场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.2 }, { id: 102, metric: '误唤醒率', value: 7.2 }, { id: 103, metric: '识别准确率', value: 87.7 }, { id: 104, metric: '平均WER', value: 9.7 }, { id: 105, metric: '平均响应时间', value: 233 }] },
        { categoryId: 'grp-farfield', categoryName: '远场场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.0 }, { id: 102, metric: '误唤醒率', value: 5.1 }, { id: 103, metric: '识别准确率', value: 90.3 }, { id: 104, metric: '平均WER', value: 8.6 }, { id: 105, metric: '平均响应时间', value: 213 }] },
      ],
    },
  ]

  const caseCategories: ReportCaseCategory[] = [
    { category_id: 'grp-wakeup', category_name: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.8 }] },
    { category_id: 'grp-noise', category_name: '噪声场景', metrics: [{ id: 103, metric: '识别准确率', value: 88.4 }] },
    { category_id: 'grp-farfield', category_name: '远场场景', metrics: [{ id: 103, metric: '识别准确率', value: 90.2 }] },
  ]

  const allCaseTags: ReportTag[] = [
    { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景' },
    { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景' },
    { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境' },
    { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型' },
    { tag_id: 't-05', tag_name: '方言', category_id: 'tag-cat-func', category_name: '功能类型' },
    { tag_id: 't-11', tag_name: '1m', category_id: 'tag-cat-dist', category_name: '距离' },
    { tag_id: 't-12', tag_name: '2m', category_id: 'tag-cat-dist', category_name: '距离' },
    { tag_id: 't-13', tag_name: '3m', category_id: 'tag-cat-dist', category_name: '距离' },
  ]

  const tagMetricData: ReportTagMetricGroup[] = [
    {
      resource: 'device_1',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.8 }, { id: 103, metric: '识别准确率', value: 90.2 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.2 }, { id: 103, metric: '识别准确率', value: 96.8 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.4 }, { id: 103, metric: '识别准确率', value: 86.1 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.5 }, { id: 105, metric: '平均响应时间', value: 412 }] },
        { tag_id: 't-11', tag_name: '1m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.6 }, { id: 103, metric: '识别准确率', value: 95.4 }] },
        { tag_id: 't-12', tag_name: '2m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 93.2 }, { id: 103, metric: '识别准确率', value: 91.6 }] },
        { tag_id: 't-13', tag_name: '3m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.9 }, { id: 103, metric: '识别准确率', value: 87.2 }] },
      ],
    },
    {
      resource: 'device_1_realtime',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.2 }, { id: 103, metric: '识别准确率', value: 89.6 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.6 }, { id: 103, metric: '识别准确率', value: 96.1 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 87.8 }, { id: 103, metric: '识别准确率', value: 85.4 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.2 }, { id: 105, metric: '平均响应时间', value: 418 }] },
        { tag_id: 't-11', tag_name: '1m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.0 }, { id: 103, metric: '识别准确率', value: 94.8 }] },
        { tag_id: 't-12', tag_name: '2m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 92.6 }, { id: 103, metric: '识别准确率', value: 90.9 }] },
        { tag_id: 't-13', tag_name: '3m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.2 }, { id: 103, metric: '识别准确率', value: 86.4 }] },
      ],
    },
    {
      resource: 'device_1_final',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.4 }, { id: 103, metric: '识别准确率', value: 90.8 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.8 }, { id: 103, metric: '识别准确率', value: 97.4 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.0 }, { id: 103, metric: '识别准确率', value: 86.8 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.8 }, { id: 105, metric: '平均响应时间', value: 405 }] },
        { tag_id: 't-11', tag_name: '1m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.2 }, { id: 103, metric: '识别准确率', value: 96.0 }] },
        { tag_id: 't-12', tag_name: '2m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 93.8 }, { id: 103, metric: '识别准确率', value: 92.2 }] },
        { tag_id: 't-13', tag_name: '3m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.5 }, { id: 103, metric: '识别准确率', value: 87.8 }] },
      ],
    },
    {
      resource: 'device_2',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 93.6 }, { id: 103, metric: '识别准确率', value: 88.9 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.4 }, { id: 103, metric: '识别准确率', value: 95.2 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 87.1 }, { id: 103, metric: '识别准确率', value: 84.6 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.8 }, { id: 105, metric: '平均响应时间', value: 415 }] },
        { tag_id: 't-11', tag_name: '1m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.8 }, { id: 103, metric: '识别准确率', value: 94.1 }] },
        { tag_id: 't-12', tag_name: '2m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 92.4 }, { id: 103, metric: '识别准确率', value: 90.3 }] },
        { tag_id: 't-13', tag_name: '3m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 87.6 }, { id: 103, metric: '识别准确率', value: 85.9 }] },
      ],
    },
    {
      resource: 'device_3',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 90.5 }, { id: 103, metric: '识别准确率', value: 86.1 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.2 }, { id: 103, metric: '识别准确率', value: 93.4 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 83.6 }, { id: 103, metric: '识别准确率', value: 81.2 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.6 }, { id: 105, metric: '平均响应时间', value: 471 }] },
        { tag_id: 't-11', tag_name: '1m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 93.9 }, { id: 103, metric: '识别准确率', value: 91.6 }] },
        { tag_id: 't-12', tag_name: '2m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.8 }, { id: 103, metric: '识别准确率', value: 88.1 }] },
        { tag_id: 't-13', tag_name: '3m', category_id: 'tag-cat-dist', category_name: '距离', metrics: [{ id: 101, metric: '唤醒成功率', value: 85.2 }, { id: 103, metric: '识别准确率', value: 83.6 }] },
      ],
    },
    {
      resource: 'api_101',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.1 }, { id: 103, metric: '识别准确率', value: 91.5 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.6 }, { id: 103, metric: '识别准确率', value: 97.1 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.2 }, { id: 103, metric: '识别准确率', value: 87.4 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.5 }, { id: 105, metric: '平均响应时间', value: 373 }] },
      ],
    },
    {
      resource: 'api_101_realtime',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.5 }, { id: 103, metric: '识别准确率', value: 90.9 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.0 }, { id: 103, metric: '识别准确率', value: 96.4 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.6 }, { id: 103, metric: '识别准确率', value: 86.7 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.1 }, { id: 105, metric: '平均响应时间', value: 380 }] },
      ],
    },
    {
      resource: 'api_101_final',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.7 }, { id: 103, metric: '识别准确率', value: 92.1 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 99.0 }, { id: 103, metric: '识别准确率', value: 97.6 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 89.8 }, { id: 103, metric: '识别准确率', value: 88.0 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.9 }, { id: 105, metric: '平均响应时间', value: 367 }] },
      ],
    },
    {
      resource: 'api_102',
      tags: [
        { tag_id: 't-01', tag_name: '远场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 94.4 }, { id: 103, metric: '识别准确率', value: 90.8 }] },
        { tag_id: 't-02', tag_name: '近场', category_id: 'tag-cat-scene', category_name: '场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 98.1 }, { id: 103, metric: '识别准确率', value: 96.5 }] },
        { tag_id: 't-03', tag_name: '噪声', category_id: 'tag-cat-env', category_name: '环境', metrics: [{ id: 101, metric: '唤醒成功率', value: 88.0 }, { id: 103, metric: '识别准确率', value: 86.5 }] },
        { tag_id: 't-04', tag_name: '唤醒', category_id: 'tag-cat-func', category_name: '功能类型', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.7 }, { id: 105, metric: '平均响应时间', value: 195 }] },
      ],
    },
  ]

  const tables: ReportComparisonTable[] = [
    {
      title: '设备/API信息对比',
      default_collapsed: true,
      columns: [
        { key: 'name', label: '名称' },
        { key: 'type', label: '类型' },
        { key: 'version', label: '版本' },
        { key: 'status', label: '状态', type: 'status' },
        { key: 'totalCases', label: '用例数', type: 'number' },
        { key: 'successRate', label: '成功率', type: 'percentage' },
      ],
      data: [
        { name: '智能音箱-旗舰-01', type: '设备', version: '3.2.1', status: 'online', totalCases: 48, successRate: 93.8 },
        { name: '智能音箱-旗舰-02', type: '设备', version: '3.2.1', status: 'offline', totalCases: 24, successRate: 95.8 },
        { name: '智能音箱-入门-03', type: '设备', version: '2.9.0', status: 'online', totalCases: 24, successRate: 91.7 },
        { name: 'asr-streaming-v3', type: 'API', version: 'v3', status: 'active', totalCases: 48, successRate: 93.8 },
        { name: 'wakeword-detect-v2', type: 'API', version: 'v2', status: 'active', totalCases: 48, successRate: 93.8 },
      ],
    },
    {
      title: '用例执行数量对比',
      default_collapsed: true,
      columns: [
        { key: 'name', label: '名称' },
        { key: 'total', label: '总数', type: 'number' },
        { key: 'executed', label: '已执行', type: 'number' },
        { key: 'completed', label: '完成', type: 'number' },
        { key: 'failed', label: '失败', type: 'number' },
        { key: 'successRate', label: '成功率', type: 'percentage' },
        { key: 'failedRate', label: '失败率', type: 'percentage' },
      ],
      data: [
        { name: '智能音箱-旗舰-01', total: 48, executed: 48, completed: 45, failed: 3, successRate: 93.8, failedRate: 6.2 },
        { name: '智能音箱-旗舰-02', total: 24, executed: 24, completed: 23, failed: 1, successRate: 95.8, failedRate: 4.2 },
        { name: '智能音箱-入门-03', total: 24, executed: 24, completed: 22, failed: 2, successRate: 91.7, failedRate: 8.3 },
        { name: 'asr-streaming-v3', total: 48, executed: 48, completed: 45, failed: 3, successRate: 93.8, failedRate: 6.2 },
        { name: 'wakeword-detect-v2', total: 48, executed: 48, completed: 45, failed: 3, successRate: 93.8, failedRate: 6.2 },
      ],
    },
  ]

  return {
    total_cases: overrides?.total_cases ?? 48,
    completed_cases: overrides?.completed_cases ?? 48,
    failed_cases: overrides?.failed_cases ?? 3,
    resources: ['device_1', 'device_1_realtime', 'device_1_final', 'device_2', 'device_3', 'api_101', 'api_101_realtime', 'api_101_final', 'api_102'],
    resource_headers: resourceHeaders,
    raw_data: rawData,
    metric_data: metricData,
    tag_metric_data: tagMetricData,
    case_categories: caseCategories,
    all_case_tags: allCaseTags,
    all_tags: allCaseTags,
    all_metrics: allMetrics,
    case_type_stats: [
      { group_id: 'grp-wakeup', group_name: '唤醒场景', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.8 }] },
      { group_id: 'grp-noise', group_name: '噪声场景', metrics: [{ id: 103, metric: '识别准确率', value: 88.4 }] },
      { group_id: 'grp-farfield', group_name: '远场场景', metrics: [{ id: 103, metric: '识别准确率', value: 90.2 }] },
    ],
    device_stats: deviceStats,
    api_stats: apiStats,
    devices: [
      { id: 1, name: '智能音箱-旗舰-01', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'online', last_online_at: '2026-10-15T08:40:00' },
      { id: 2, name: '智能音箱-旗舰-02', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'offline', last_online_at: '2026-10-14T19:10:00' },
      { id: 3, name: '智能音箱-入门-03', model: 'Xiaomi Speaker Lite', type: 'smart_speaker', system: 'MIUI Home', system_version: '2.9.0', status: 'online', last_online_at: '2026-10-15T08:38:00' },
    ],
    apis: [
      { id: 101, name: 'asr-streaming-v3', vendor: '内部 ASR', status: 'active', max_process: 32, health_score: 0.92 },
      { id: 102, name: 'wakeword-detect-v2', vendor: '内部唤醒', status: 'active', max_process: 16, health_score: 0.88 },
    ],
    tables,
    field_mappings: [
      {
        algorithmType: {
          result: ['asr_text', 'transcript', 'wer_score'],
          reference: ['reference_text', 'stmRef', 'rttmRef'],
        },
      },
    ],
    get cases() { return MOCK_REPORT_CASES },
    detailed_results: [],
  }
}

function buildTaskReportDetail(): ReportDetailData {
  return {
    id: 1201,
    name: '旗舰音箱全量回归 · 第 3 轮报告',
    type: 'task',
    task_id: 1042,
    task_type: 'e2e',
    task_name: '智能音箱旗舰机型全量回归 · 第 3 轮',
    algorithm_type: 'asr_streaming',
    description: '旗舰音箱第 3 轮全量回归：48 条用例覆盖唤醒、识别与误触场景。',
    status: 'published',
    analysis:
      '本轮回归共执行 48 条用例，整体通过率 93.8%。唤醒成功率在近场场景表现稳定（≥96%），噪声场景下识别准确率降至 88.4%，建议重点优化远场与噪声组合场景的唤醒阈值。\n\nasr-streaming-v3 与 wakeword-detect-v2 双算法对比：流式识别平均响应 385ms，优于唤醒检测链路（201ms 响应但后续转写链路略增延迟）。入门机型（智能音箱-入门-03）识别准确率较旗舰低约 2.4 个百分点，属预期硬件差异。',
    summary: buildTaskSummary(),
    created_at: '2026-10-15T09:20:00',
    updated_at: '2026-10-15T09:20:00',
  }
}

function buildComparisonReportDetail(type: 'comparison' | 'secondary_comparison'): ReportDetailData {
  const isSecondary = type === 'secondary_comparison'

  const comparisonDevices: ReportDeviceInfo[] = [
    { id: 1, name: '智能音箱-旗舰-01', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'online', last_online_at: '2026-10-15T08:40:00' },
    { id: 2, name: '智能音箱-旗舰-02', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'offline', last_online_at: '2026-10-14T19:10:00' },
    { id: 3, name: '智能音箱-入门-03', model: 'Xiaomi Speaker Lite', type: 'smart_speaker', system: 'MIUI Home', system_version: '2.9.0', status: 'online', last_online_at: '2026-10-15T08:38:00' },
  ]
  const comparisonApis: ReportApiInfo[] = [
    { id: 101, name: 'asr-streaming-v3', vendor: '内部 ASR', status: 'active', max_process: 32, health_score: 0.92 },
    { id: 102, name: 'wakeword-detect-v2', vendor: '内部唤醒', status: 'active', max_process: 16, health_score: 0.88 },
  ]

  const baseSummary: ReportSummary = {
    total_cases: 48,
    completed_cases: 48,
    failed_cases: 3,
    task_count: 4,
    resources: ['task_1041', 'task_1037', 'task_1035', 'task_1042'],
    resource_headers: [
      { key: 'task_1041', label: '车载语音助手唤醒词响应测试', type: 'task', id: 1041, name: '车载语音助手唤醒词响应测试' },
      { key: 'task_1037', label: '多方言识别准确性抽样测试', type: 'task', id: 1037, name: '多方言识别准确性抽样测试' },
      { key: 'task_1035', label: 'Q3 音箱品类回归汇总（合并自 4 个任务）', type: 'task', id: 1035, name: 'Q3 音箱品类回归汇总' },
      { key: 'task_1042', label: '智能音箱旗舰机型全量回归 · 第 3 轮', type: 'task', id: 1042, name: '智能音箱旗舰机型全量回归 · 第 3 轮' },
    ],
    raw_data: [],
    metric_data: [
      { resource: 'task_1041', metrics: [{ id: 101, metric: '唤醒成功率', value: 96.2 }, { id: 103, metric: '识别准确率', value: 92.1 }, { id: 105, metric: '平均响应时间', value: 205 }] },
      { resource: 'task_1037', metrics: [{ id: 101, metric: '唤醒成功率', value: 90.4 }, { id: 103, metric: '识别准确率', value: 84.7 }, { id: 105, metric: '平均响应时间', value: 390 }] },
      { resource: 'task_1035', metrics: [{ id: 101, metric: '唤醒成功率', value: 97.1 }, { id: 103, metric: '识别准确率', value: 96.9 }, { id: 105, metric: '平均响应时间', value: 402 }] },
      { resource: 'task_1042', metrics: [{ id: 101, metric: '唤醒成功率', value: 95.8 }, { id: 103, metric: '识别准确率', value: 93.8 }, { id: 105, metric: '平均响应时间', value: 412 }] },
    ],
    tag_metric_data: [],
    case_categories: [],
    all_case_tags: [],
    all_tags: [],
    all_metrics: [
      { id: 101, name: '唤醒成功率', unit: '%', decimal_places: 1, dimension_type: 'main' },
      { id: 103, name: '识别准确率', unit: '%', decimal_places: 1, dimension_type: 'main' },
      { id: 105, name: '平均响应时间', unit: 'ms', decimal_places: 0, dimension_type: 'main' },
    ],
    case_type_stats: [],
    device_stats: [
      { id: 1, name: '智能音箱-旗舰-01', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'online', total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8, metrics: { 唤醒成功率: 96.5 } },
      { id: 2, name: '智能音箱-旗舰-02', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'offline', total_cases: 24, completed_cases: 24, failed_cases: 1, success_rate: 95.8, metrics: { 唤醒成功率: 95.4 } },
    ],
    api_stats: [
      { id: 101, name: 'asr-streaming-v3', status: 'active', max_process: 32, health_score: 0.92, total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8, avg_response_time: 385, stability: 0.98, metrics: { 平均响应时间: 385, 稳定性: 0.98 } },
      { id: 102, name: 'wakeword-detect-v2', status: 'active', max_process: 16, health_score: 0.88, total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8, avg_response_time: 201, stability: 0.99, metrics: { 平均响应时间: 201, 稳定性: 0.99 } },
    ],
    devices: comparisonDevices,
    apis: comparisonApis,
    tables: [
      {
        title: '设备/API信息对比',
        default_collapsed: true,
        columns: [
          { key: 'name', label: '名称' },
          { key: 'type', label: '类型' },
          { key: 'version', label: '版本' },
          { key: 'status', label: '状态', type: 'status' },
          { key: 'totalCases', label: '用例数', type: 'number' },
          { key: 'successRate', label: '成功率', type: 'percentage' },
        ],
        data: [
          { name: '智能音箱-旗舰-01', type: '设备', version: '3.2.1', status: 'online', totalCases: 48, successRate: 93.8 },
          { name: '智能音箱-旗舰-02', type: '设备', version: '3.2.1', status: 'offline', totalCases: 24, successRate: 95.8 },
          { name: 'asr-streaming-v3', type: 'API', version: 'v3', status: 'active', totalCases: 48, successRate: 93.8 },
          { name: 'wakeword-detect-v2', type: 'API', version: 'v2', status: 'active', totalCases: 48, successRate: 93.8 },
        ],
      },
      {
        title: '用例执行数量对比',
        default_collapsed: true,
        columns: [
          { key: 'name', label: '名称' },
          { key: 'total', label: '总数', type: 'number' },
          { key: 'executed', label: '已执行', type: 'number' },
          { key: 'completed', label: '完成', type: 'number' },
          { key: 'failed', label: '失败', type: 'number' },
          { key: 'successRate', label: '成功率', type: 'percentage' },
          { key: 'failedRate', label: '失败率', type: 'percentage' },
        ],
        data: [
          { name: '智能音箱-旗舰-01', total: 48, executed: 48, completed: 45, failed: 3, successRate: 93.8, failedRate: 6.2 },
          { name: '智能音箱-旗舰-02', total: 24, executed: 24, completed: 23, failed: 1, successRate: 95.8, failedRate: 4.2 },
          { name: 'asr-streaming-v3', total: 48, executed: 48, completed: 45, failed: 3, successRate: 93.8, failedRate: 6.2 },
          { name: 'wakeword-detect-v2', total: 48, executed: 48, completed: 45, failed: 3, successRate: 93.8, failedRate: 6.2 },
        ],
      },
    ],
    field_mappings: [
      { algorithmType: { result: ['asr_text', 'transcript'], reference: ['reference_text'] } },
    ],
    cases: [],
    detailed_results: [],
  }

  if (isSecondary) {
    return {
      id: 1188,
      name: '二次对比：方言识别 × 噪声场景',
      type,
      task_id: undefined,
      task_type: undefined,
      task_name: '3 个报告对比',
      algorithm_type: 'asr_streaming',
      description: '基于报告 1197/1200/1201 的二次对比：噪声场景下的识别差异。',
      status: 'published',
      analysis:
        '二次对比显示：在噪声场景下，方言识别准确率整体下降约 6 个百分点；旗舰音箱的波束成形对车载噪声的抑制优于单麦克风链路。',
      summary: baseSummary,
      created_at: '2026-10-15T11:30:00',
      updated_at: '2026-10-15T11:30:00',
    }
  }

  return {
    id: 1190,
    name: '旗舰音箱 vs 车载助手 唤醒性能对比报告',
    type,
    task_id: undefined,
    task_type: undefined,
    task_name: '4 个任务对比',
    algorithm_type: 'wakeword_detect',
    description: '对比任务 1041/1037/1035/1042 的唤醒性能与识别准确率差异。',
    status: 'published',
    analysis:
      '四任务对比显示：车载助手唤醒响应（wakeword-detect-v2）在近场表现最优；旗舰音箱在远场识别准确率上领先约 3 个百分点。',
    summary: baseSummary,
    created_at: '2026-10-15T10:02:00',
    updated_at: '2026-10-15T10:02:00',
  }
}

/** 具体用例列表 mock（POST /reports/{id}/cases/search 形态；build_case_item 全字段，§1.3） */
const MOCK_REPORT_CASES: ReportCaseItem[] = [
  {
    id: 'c-1042-001',
    name: '远场唤醒-客厅 3 米',
    description: '客厅 3 米距离，环境噪声 35dB，测试两次唤醒词响应。',
    category: 'grp-farfield',
    tags: ['远场', '唤醒'],
    algorithmType: 'asr_streaming',
    metrics: {
      device_1_realtime: { 唤醒成功率: 100, 识别准确率: 96.8, 平均响应时间: 418 },
      device_1_final: { 唤醒成功率: 100, 识别准确率: 97.5, 平均响应时间: 412 },
      api_101_realtime: { 唤醒成功率: 100, 识别准确率: 97.2, 平均响应时间: 396 },
      api_101_final: { 唤醒成功率: 100, 识别准确率: 97.9, 平均响应时间: 390 },
    },
    results: [
      { resource: 'device_1_realtime', status: 'completed', result_type: 'realtime', startTime: '2026-10-15T08:42:00', endTime: '2026-10-15T08:42:02' },
      { resource: 'device_1_final', status: 'completed', result_type: 'final', startTime: '2026-10-15T08:42:01', endTime: '2026-10-15T08:42:02' },
      { resource: 'api_101_realtime', status: 'completed', result_type: 'realtime', startTime: '2026-10-15T08:42:00', endTime: '2026-10-15T08:42:01' },
      { resource: 'api_101_final', status: 'completed', result_type: 'final', startTime: '2026-10-15T08:42:01', endTime: '2026-10-15T08:42:01' },
    ],
    audios: [
      { audio_id: 'a-9001', audio_name: '唤醒词-远场-客厅.wav', audio_type: 'wakeword', spl: 55, play_order: 1, noise_spl: 35, device_name: '智能音箱-旗舰-01' },
      { audio_id: 'a-9011', audio_name: '唤醒词-远场-客厅-最终.wav', audio_type: 'final', spl: 55, play_order: 2, noise_spl: 35, device_name: '智能音箱-旗舰-01' },
    ],
    referenceParams: {
      asr_text: { code: 'asr_text', type: 'text', label: '识别文本', value: '小爱同学，今天天气怎么样？' },
    },
    caseParams: {
      wakeword: { code: 'wakeword', type: 'text', label: '唤醒词', value: '小爱同学' },
      distance: { code: 'distance', type: 'number', label: '距离', value: 3 },
      noise: { code: 'noise', type: 'number', label: '环境噪声', value: 35 },
    },
    algorithmResults: [
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，今天天气怎么样？', device: 'device_1_realtime' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，今天天气怎么样？', device: 'device_1_final' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，今天天气怎么样？', device: 'api_101_realtime' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，今天天气怎么样？', device: 'api_101_final' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 2.1, device: 'device_1_realtime' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 1.9, device: 'device_1_final' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 1.8, device: 'api_101_realtime' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 1.6, device: 'api_101_final' },
    ],
    overall_status: 'pass',
    logs: '[2026-10-15 08:42:01] 唤醒词检测命中\n[2026-10-15 08:42:01] ASR 请求 -> asr-streaming-v3\n[2026-10-15 08:42:02] ASR 响应 418ms\n[2026-10-15 08:42:02] 文本匹配成功 (相似度 0.98)',
  },
  {
    id: 'c-1042-002',
    name: '噪声场景-厨房设备运行',
    description: '厨房设备运行噪声 60dB，测试唤醒词误唤醒与识别。',
    category: 'grp-noise',
    tags: ['噪声', '唤醒'],
    algorithmType: 'asr_streaming',
    metrics: {
      device_1_realtime: { 唤醒成功率: 66.7, 识别准确率: 78.2, 平均响应时间: 536 },
      device_1_final: { 唤醒成功率: 66.7, 识别准确率: 79.0, 平均响应时间: 528 },
      api_101_realtime: { 唤醒成功率: 66.7, 识别准确率: 80.1, 平均响应时间: 512 },
      api_101_final: { 唤醒成功率: 66.7, 识别准确率: 80.9, 平均响应时间: 505 },
    },
    results: [
      { resource: 'device_1_realtime', status: 'failed', result_type: 'realtime', startTime: '2026-10-15T08:50:11', endTime: '2026-10-15T08:50:12' },
      { resource: 'device_1_final', status: 'failed', result_type: 'final', startTime: '2026-10-15T08:50:12', endTime: '2026-10-15T08:50:12' },
      { resource: 'api_101_realtime', status: 'completed', result_type: 'realtime', startTime: '2026-10-15T08:50:11', endTime: '2026-10-15T08:50:12' },
      { resource: 'api_101_final', status: 'completed', result_type: 'final', startTime: '2026-10-15T08:50:12', endTime: '2026-10-15T08:50:12' },
    ],
    audios: [
      { audio_id: 'a-9002', audio_name: '唤醒词-噪声-厨房.wav', audio_type: 'wakeword', spl: 58, play_order: 1, noise_spl: 60, device_name: '智能音箱-旗舰-01' },
    ],
    referenceParams: {
      asr_text: { code: 'asr_text', type: 'text', label: '识别文本', value: '小爱同学，播放一首歌' },
    },
    algorithmResults: [
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，播放一首歌', device: 'device_1_realtime' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，播放一首歌', device: 'device_1_final' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，播放一首歌', device: 'api_101_realtime' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，播放一首歌', device: 'api_101_final' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 12.4, device: 'device_1_realtime' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 11.8, device: 'device_1_final' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 10.2, device: 'api_101_realtime' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 9.6, device: 'api_101_final' },
    ],
    overall_status: 'fail',
    logs: '[2026-10-15 08:50:11] 唤醒词检测命中\n[2026-10-15 08:50:12] ASR 响应 536ms\n[2026-10-15 08:50:12] wakeword-detect-v2 转写超时，降级重试',
  },
  {
    id: 'c-1042-003',
    name: '近场唤醒-桌面 0.5 米',
    description: '桌面 0.5 米，安静环境，唤醒词连续三次。',
    category: 'grp-wakeup',
    tags: ['近场', '唤醒'],
    algorithmType: 'asr_streaming',
    metrics: {
      device_2: { 唤醒成功率: 100, 识别准确率: 98.2, 平均响应时间: 212 },
    },
    metricScore: { 唤醒成功率: 5, 识别准确率: 4, 平均响应时间: 5 },
    metricError: {
      识别准确率:
        '近场桌面识别存在轻微漏字，置信度 0.92，建议复核超长指令；唤醒词命中率 100%，但识别文本与参考存在一字之差，属于低风险偏差，建议结合上下文综合判定后归档（§3.5.1 长错误可折叠）。',
    },
    caseParams: {
      wakeword: { code: 'wakeword', type: 'text', label: '唤醒词', value: '小爱同学' },
      distance: { code: 'distance', type: 'number', label: '距离', value: 0.5 },
      environment: { code: 'environment', type: 'text', label: '环境', value: '安静室内' },
    },
    results: [
      { resource: 'device_2', status: 'completed', startTime: '2026-10-15T08:58:31', endTime: '2026-10-15T08:58:31' },
      { resource: 'api_101', status: 'completed', startTime: '2026-10-15T08:58:31', endTime: '2026-10-15T08:58:31' },
    ],
    audios: [
      { audio_id: 'a-9003', audio_name: '唤醒词-近场-桌面.wav', audio_type: 'wakeword', spl: 62, play_order: 1, noise_spl: 30, device_name: '智能音箱-旗舰-02' },
    ],
    referenceParams: {
      asr_text: { code: 'asr_text', type: 'text', label: '识别文本', value: '小爱同学，明天早上叫我起床' },
    },
    algorithmResults: [
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，明天早上叫我起床', device: 'device_2' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '小爱同学，明天早上叫我起床', device: 'api_101' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 0.8, device: 'device_2' },
      { paramCode: 'wer_score', paramType: 'number', label: 'WER 评分', value: 0.6, device: 'api_101' },
    ],
    overall_status: 'pass',
    logs: '[2026-10-15 08:58:31] 唤醒词检测命中\n[2026-10-15 08:58:31] ASR 响应 212ms',
  },
  {
    id: 'c-1042-004',
    name: '方言识别-粤语日常指令',
    description: '粤语日常指令识别，安静环境。',
    category: 'grp-wakeup',
    tags: ['方言', '近场'],
    algorithmType: 'asr_streaming',
    metrics: {
      device_1: { 唤醒成功率: 100, 识别准确率: 91.5, 平均响应时间: 388 },
      api_101: { 唤醒成功率: 100, 识别准确率: 92.6, 平均响应时间: 372 },
    },
    results: [
      { resource: 'device_1', status: 'completed', startTime: '2026-10-15T09:02:01', endTime: '2026-10-15T09:02:02' },
      { resource: 'api_101', status: 'completed', startTime: '2026-10-15T09:02:01', endTime: '2026-10-15T09:02:01' },
    ],
    audios: [],
    referenceParams: {
      asr_text: { code: 'asr_text', type: 'text', label: '识别文本', value: '帮我睇下听日天气' },
    },
    algorithmResults: [
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '帮我睇下听日天气', device: 'device_1' },
      { paramCode: 'asr_text', paramType: 'text', label: '识别文本', value: '帮我睇下听日天气', device: 'api_101' },
      { paramCode: 'trans_result', paramType: 'text', label: '翻译结果', value: '帮我看看明天天气', device: 'device_1' },
      { paramCode: 'trans_result', paramType: 'text', label: '翻译结果', value: '帮我看看明天天气', device: 'api_101' },
    ],
    overall_status: 'pass',
    logs: '[2026-10-15 09:02:01] ASR 请求 -> asr-streaming-v3\n[2026-10-15 09:02:02] 翻译链路启用 粤语→普通话',
  },
  {
    id: 'c-1042-005',
    name: '多轮对话-闲聊上下文（voice_llm）',
    description: 'voice_llm 三轮连续对话，验证上下文保持与每轮 WER/LLM 评分。',
    category: 'grp-wakeup',
    tags: ['近场', '唤醒'],
    algorithmType: 'voice_llm',
    metrics: [
      {
        resource: 'device_1',
        metrics: [
          { id: 104, metric: '平均WER@round:1', value: 4.2, score: 4, error: '第 1 轮 WER 4.2%，受环境噪声影响，建议复核。' },
          { id: 105, metric: '平均响应时间@round:1', value: 342, score: 5 },
          { id: 104, metric: '平均WER@round:2', value: 3.1, score: 5 },
          { id: 105, metric: '平均响应时间@round:2', value: 338, score: 5 },
          { id: 104, metric: '平均WER@round:3', value: 6.5, score: 3, error: '第 3 轮 WER 6.5%，上下文保持良好但收尾语气停顿略长，建议优化多轮衔接。' },
          { id: 105, metric: '平均响应时间@round:3', value: 356, score: 4 },
          { id: 104, metric: '平均WER', value: 4.6, score: 4 },
          { id: 105, metric: '平均响应时间', value: 345, score: 5 },
        ],
      },
      {
        resource: 'api_101',
        metrics: [
          { id: 104, metric: '平均WER@round:1', value: 3.6, score: 5 },
          { id: 105, metric: '平均响应时间@round:1', value: 318, score: 5 },
          { id: 104, metric: '平均WER@round:2', value: 2.8, score: 5 },
          { id: 105, metric: '平均响应时间@round:2', value: 315, score: 5 },
          { id: 104, metric: '平均WER@round:3', value: 5.8, score: 4 },
          { id: 105, metric: '平均响应时间@round:3', value: 331, score: 5 },
          { id: 104, metric: '平均WER', value: 4.0, score: 5 },
          { id: 105, metric: '平均响应时间', value: 321, score: 5 },
        ],
      },
    ],
    caseParams: {
      'prompt@round:1': { code: 'prompt@round:1', type: 'text', label: '第1轮提问', value: '请回答：今天天气怎么样？' },
      'prompt@round:2': { code: 'prompt@round:2', type: 'text', label: '第2轮提问', value: '请回答：明天天气怎么样？' },
      'prompt@round:3': { code: 'prompt@round:3', type: 'text', label: '第3轮提问', value: '请回答：还有什么需要帮忙的吗？' },
    },
    results: [
      { resource: 'device_1', status: 'completed', startTime: '2026-10-15T09:05:00', endTime: '2026-10-15T09:05:06' },
      { resource: 'api_101', status: 'completed', startTime: '2026-10-15T09:05:00', endTime: '2026-10-15T09:05:05' },
    ],
    audios: [
      { audio_id: 'a-9004', audio_name: '对话-第1轮.wav', audio_type: 'dialogue', spl: 58, play_order: 1, noise_spl: 32, device_name: '智能音箱-旗舰-01' },
    ],
    referenceParams: {
      'answer@round:1': { code: 'answer@round:1', type: 'text', label: '参考回答 (第1轮)', value: '好的，我已经记住今天的天气了。' },
      'answer@round:2': { code: 'answer@round:2', type: 'text', label: '参考回答 (第2轮)', value: '明天多云，出门记得带伞。' },
      'answer@round:3': { code: 'answer@round:3', type: 'text', label: '参考回答 (第3轮)', value: '好的，还有什么需要帮忙的吗？' },
    },
    algorithmResults: [
      {
        paramCode: 'answer@round:1', paramType: 'text', label: 'answer (第1轮)', roundNumber: 1, value: '好的，我已经记住今天的天气了。', device: 'device_1',
      },
      {
        paramCode: 'answer@round:1', paramType: 'text', label: 'answer (第1轮)', roundNumber: 1, value: '好的，我已经记住今天的天气了。', device: 'api_101',
      },
      {
        paramCode: 'answer@round:2', paramType: 'text', label: 'answer (第2轮)', roundNumber: 2, value: '明天多云，出门记得带伞。', device: 'device_1',
      },
      {
        paramCode: 'answer@round:2', paramType: 'text', label: 'answer (第2轮)', roundNumber: 2, value: '明天多云，出门记得带伞。', device: 'api_101',
      },
      {
        paramCode: 'answer@round:3', paramType: 'text', label: 'answer (第3轮)', roundNumber: 3, value: '好的，还有什么需要帮忙的吗？', device: 'device_1',
      },
      {
        paramCode: 'answer@round:3', paramType: 'text', label: 'answer (第3轮)', roundNumber: 3, value: '好的，还有什么需要帮忙的吗？', device: 'api_101',
      },
      {
        paramCode: 'multi_round_result', paramType: 'json', label: '多轮结果', device: 'device_1',
        rounds: [
          {
            round: 0,
            input: { audio_name: '对话-第1轮.wav' },
            output: { asr_text: '好的，我已经记住今天的天气了。' },
            evaluation: { wer: 4.2, llm_judge: 9.1, latency: 342, reasoning: '回答自然，上下文保持良好。' },
            interruption: { detected: false },
          },
          {
            round: 1,
            input: { audio_name: '对话-第2轮.wav' },
            output: { asr_text: '明天多云，出门记得带伞。' },
            evaluation: { wer: 3.1, llm_judge: 9.4, latency: 338, reasoning: '信息准确，语气连贯。' },
            interruption: { detected: false },
          },
          {
            round: 2,
            input: { audio_name: '对话-第3轮.wav' },
            output: { asr_text: '好的，还有什么需要帮忙的吗？' },
            evaluation: { wer: 6.5, llm_judge: 8.6, latency: 356, reasoning: '收尾自然，等待用户继续。' },
            interruption: { detected: true },
          },
        ],
      },
    ],
    overall_status: 'pass',
    logs: '[2026-10-15 09:05:00] voice_llm 三轮对话执行\n[2026-10-15 09:05:06] 多轮聚合：平均 WER 4.6% / LLM 评分 9.0 / 延迟 345ms',
  },
  {
    id: 'c-1042-006',
    name: '误触测试-连续播报中唤醒',
    description: '播报持续中唤醒词误触，本轮跳过（人工复核）。',
    category: 'grp-noise',
    tags: ['噪声', '唤醒'],
    algorithmType: 'wakeword_detect',
    metrics: {},
    results: [
      { resource: 'device_1', status: 'skipped', startTime: '2026-10-15T09:10:00', endTime: '2026-10-15T09:10:00' },
    ],
    audios: [],
    overall_status: 'skip',
    logs: '[2026-10-15 09:10:00] 用例标记跳过（人工复核）',
  },
] satisfies ReportCaseItem[]

export const MOCK_REPORT_CASE_LIST_DATA: ReportCaseListData = {
  items: MOCK_REPORT_CASES,
  total: MOCK_REPORT_CASES.length,
  page: 1,
  per_page: 20,
  pages: 1,
}
