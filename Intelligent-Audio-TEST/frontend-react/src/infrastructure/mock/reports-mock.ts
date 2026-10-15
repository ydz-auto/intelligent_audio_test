/**
 * 报告域 mock 常量（红线④：数据一律 mock，不接真实后端）。
 * 字段形态对照 api_gateway/schemas/report.py 实测 schema（见 domain/models/report.ts），
 * 数字口径与基座控制台 mock（任务 342/已完成 297、设备 8 在线/2 离线）互不打架。
 * 列表与详情 id 联动：1201=任务报告、1190=对比报告、1188=二次对比报告，供详情页/行菜单跳转核对。
 */
import type {
  ReportApiStat,
  ReportCaseCategory,
  ReportCaseItem,
  ReportCaseListData,
  ReportDetailData,
  ReportDeviceStat,
  ReportListItem,
  ReportListData,
  ReportTabCounts,
  ReportTag,
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
] satisfies ReportListItem[]

/** GET /reports 服务端分页响应 mock（useReportList 按 page/per_page 切片） */
export const MOCK_REPORT_LIST_DATA: ReportListData = {
  items: MOCK_REPORT_LIST_ITEMS,
  total: MOCK_REPORT_LIST_ITEMS.length,
  page: 1,
  per_page: 20,
  pages: 1,
}

/** GET /reports/tab-counts（all/draft/published/comparison） */
export const MOCK_REPORT_TAB_COUNTS: ReportTabCounts = {
  all: 12,
  draft: 3,
  published: 9,
  comparison: 3,
}

/** 报告头算法徽标色板数据源（算法枚举，对照 api_gateway/schemas/algorithm.py 实测名） */
export const REPORT_ALGORITHMS = [
  'asr_streaming',
  'asr_offline',
  'wakeword_detect',
  'tts_eval',
  'spl_eval',
] as const

/** 生成报告 Dialog 任务选择器（GET /tasks 只读子集：已完成任务） */
export const MOCK_COMPLETED_TASKS = [
  { id: 1041, name: '车载语音助手唤醒词响应测试', type: 'e2e', status: 'completed', completed_at: '2026-10-14T17:05:00' },
  { id: 1037, name: '多方言识别准确性抽样测试', type: 'api', status: 'completed', completed_at: '2026-10-13T11:02:00' },
  { id: 1035, name: 'Q3 音箱品类回归汇总（合并自 4 个任务）', type: 'mixed', status: 'completed', completed_at: '2026-10-11T10:00:00' },
  { id: 1015, name: 'TTS 自然度主观评估（第 1 期）', type: 'api', status: 'completed', completed_at: '2026-09-28T09:30:00' },
] as const

/** 报告详情 mock 源（key=报告 id；消费方按 id 取，缺省回退 1201） */
export const MOCK_REPORT_DETAILS: Record<number, ReportDetailData> = {
  1201: buildTaskReportDetail(),
  1190: buildComparisonReportDetail('comparison'),
  1188: buildComparisonReportDetail('secondary_comparison'),
}

function buildTaskReportDetail(): ReportDetailData {
  const deviceStats: ReportDeviceStat[] = [
    {
      id: 1, name: '智能音箱-旗舰-01', model: 'Xiaomi Speaker Pro', type: 'smart_speaker',
      system: 'MIUI Home', system_version: '3.2.1', status: 'online',
      total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8,
      metrics: { 唤醒成功率: 96.5, 平均响应: 412, 稳定性: 0.98 },
    },
    {
      id: 2, name: '智能音箱-旗舰-02', model: 'Xiaomi Speaker Pro', type: 'smart_speaker',
      system: 'MIUI Home', system_version: '3.2.1', status: 'offline',
      total_cases: 24, completed_cases: 24, failed_cases: 1, success_rate: 95.8,
      metrics: { 唤醒成功率: 95.4, 平均响应: 428, 稳定性: 0.97 },
    },
    {
      id: 3, name: '智能音箱-入门-03', model: 'Xiaomi Speaker Lite', type: 'smart_speaker',
      system: 'MIUI Home', system_version: '2.9.0', status: 'online',
      total_cases: 24, completed_cases: 24, failed_cases: 2, success_rate: 91.7,
      metrics: { 唤醒成功率: 93.1, 平均响应: 486, 稳定性: 0.95 },
    },
  ]
  const deviceApiStats: ReportApiStat[] = [
    {
      id: 101, name: 'asr-streaming-v3', status: 'active', max_process: 32, health_score: 0.92,
      total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8,
      avg_response_time: 385, stability: 0.98, metrics: { 平均响应: 385, 稳定性: 0.98 },
    },
    {
      id: 102, name: 'wakeword-detect-v2', status: 'active', max_process: 16, health_score: 0.88,
      total_cases: 48, completed_cases: 48, failed_cases: 3, success_rate: 93.8,
      avg_response_time: 201, stability: 0.99, metrics: { 平均响应: 201, 稳定性: 0.99 },
    },
  ]

  const resourceHeaders = [
    { key: 'device_1', label: '智能音箱-旗舰-01', type: 'device', id: 1, name: '智能音箱-旗舰-01' },
    { key: 'device_2', label: '智能音箱-旗舰-02', type: 'device', id: 2, name: '智能音箱-旗舰-02' },
    { key: 'device_3', label: '智能音箱-入门-03', type: 'device', id: 3, name: '智能音箱-入门-03' },
    { key: 'api_101', label: 'asr-streaming-v3', type: 'api', id: 101, name: 'asr-streaming-v3' },
    { key: 'api_102', label: 'wakeword-detect-v2', type: 'api', id: 102, name: 'wakeword-detect-v2' },
  ]

  const metricData = [
    {
      resource: 'device_1',
      metrics: [
        { id: 1, metric: '唤醒成功率', value: 96.5 },
        { id: 2, metric: '识别准确率', value: 94.2 },
        { id: 3, metric: '平均响应时间(ms)', value: 412 },
      ],
    },
    {
      resource: 'device_2',
      metrics: [
        { id: 1, metric: '唤醒成功率', value: 95.4 },
        { id: 2, metric: '识别准确率', value: 93.1 },
        { id: 3, metric: '平均响应时间(ms)', value: 428 },
      ],
    },
    {
      resource: 'device_3',
      metrics: [
        { id: 1, metric: '唤醒成功率', value: 93.1 },
        { id: 2, metric: '识别准确率', value: 91.8 },
        { id: 3, metric: '平均响应时间(ms)', value: 486 },
      ],
    },
    {
      resource: 'api_101',
      metrics: [
        { id: 1, metric: '唤醒成功率', value: 96.0 },
        { id: 2, metric: '识别准确率', value: 94.5 },
        { id: 3, metric: '平均响应时间(ms)', value: 385 },
      ],
    },
    {
      resource: 'api_102',
      metrics: [
        { id: 1, metric: '唤醒成功率', value: 95.2 },
        { id: 2, metric: '识别准确率', value: 92.7 },
        { id: 3, metric: '平均响应时间(ms)', value: 201 },
      ],
    },
  ]

  const caseCategories: ReportCaseCategory[] = [
    { category_id: 'grp-wakeup', category_name: '唤醒场景', metrics: [{ id: 1, metric: '唤醒成功率', value: 95.8 }] },
    { category_id: 'grp-noise', category_name: '噪声场景', metrics: [{ id: 1, metric: '识别准确率', value: 88.4 }] },
    { category_id: 'grp-farfield', category_name: '远场场景', metrics: [{ id: 1, metric: '识别准确率', value: 90.2 }] },
  ]

  const allCaseTags: ReportTag[] = [
    { tag_id: 't-01', tag_name: '远场' },
    { tag_id: 't-02', tag_name: '近场' },
    { tag_id: 't-03', tag_name: '噪声' },
    { tag_id: 't-04', tag_name: '唤醒' },
    { tag_id: 't-05', tag_name: '方言' },
  ]

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
    summary: {
      total_cases: 48,
      completed_cases: 48,
      failed_cases: 3,
      resources: ['device_1', 'device_2', 'device_3', 'api_101', 'api_102'],
      resource_headers: resourceHeaders,
      metric_data: metricData,
      case_categories: caseCategories,
      all_case_tags: allCaseTags,
      all_metrics: ['唤醒成功率', '识别准确率', '平均响应时间(ms)'],
      device_stats: deviceStats,
      api_stats: deviceApiStats,
      devices: [
        { id: 1, name: '智能音箱-旗舰-01', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'online', last_online_at: '2026-10-15T08:40:00' },
        { id: 2, name: '智能音箱-旗舰-02', model: 'Xiaomi Speaker Pro', type: 'smart_speaker', system: 'MIUI Home', system_version: '3.2.1', status: 'offline', last_online_at: '2026-10-14T19:10:00' },
        { id: 3, name: '智能音箱-入门-03', model: 'Xiaomi Speaker Lite', type: 'smart_speaker', system: 'MIUI Home', system_version: '2.9.0', status: 'online', last_online_at: '2026-10-15T08:38:00' },
      ],
      apis: [
        { id: 101, name: 'asr-streaming-v3', vendor: '内部 ASR', status: 'active', max_process: 32, health_score: 0.92 },
        { id: 102, name: 'wakeword-detect-v2', vendor: '内部唤醒', status: 'active', max_process: 16, health_score: 0.88 },
      ],
    },
    created_at: '2026-10-15T09:20:00',
    updated_at: '2026-10-15T09:20:00',
  }
}

function buildComparisonReportDetail(type: 'comparison' | 'secondary_comparison'): ReportDetailData {
  const isSecondary = type === 'secondary_comparison'
  return {
    id: isSecondary ? 1188 : 1190,
    name: isSecondary
      ? '二次对比：方言识别 × 噪声场景'
      : '旗舰音箱 vs 车载助手 唤醒性能对比报告',
    type,
    task_id: undefined,
    task_type: undefined,
    task_name: isSecondary ? '3 个报告对比' : '4 个任务对比',
    algorithm_type: 'wakeword_detect',
    description: isSecondary
      ? '基于报告 1197/1200/1201 的二次对比：噪声场景下的识别差异。'
      : '对比任务 1041/1037/1035/1042 的唤醒性能与识别准确率差异。',
    status: 'published',
    analysis: isSecondary
      ? '二次对比显示：在噪声场景下，方言识别准确率整体下降约 6 个百分点；旗舰音箱的波束成形对车载噪声的抑制优于单麦克风链路。'
      : '四任务对比显示：车载助手唤醒响应（wakeword-detect-v2）在近场表现最优；旗舰音箱在远场识别准确率上领先约 3 个百分点。',
    summary: {
      total_cases: 0,
      completed_cases: 0,
      failed_cases: 0,
      resources: ['task_1041', 'task_1037', 'task_1035', 'task_1042'],
      resource_headers: [
        { key: 'task_1041', label: '车载语音助手唤醒词响应测试', type: 'task', id: 1041, name: '车载语音助手唤醒词响应测试' },
        { key: 'task_1037', label: '多方言识别准确性抽样测试', type: 'task', id: 1037, name: '多方言识别准确性抽样测试' },
        { key: 'task_1035', label: 'Q3 音箱品类回归汇总（合并自 4 个任务）', type: 'task', id: 1035, name: 'Q3 音箱品类回归汇总' },
        { key: 'task_1042', label: '智能音箱旗舰机型全量回归 · 第 3 轮', type: 'task', id: 1042, name: '智能音箱旗舰机型全量回归 · 第 3 轮' },
      ],
      metric_data: [
        { resource: 'task_1041', metrics: [{ id: 1, metric: '唤醒成功率', value: 96.2 }, { id: 2, metric: '识别准确率', value: 92.1 }, { id: 3, metric: '平均响应时间(ms)', value: 205 }] },
        { resource: 'task_1037', metrics: [{ id: 1, metric: '唤醒成功率', value: 90.4 }, { id: 2, metric: '识别准确率', value: 84.7 }, { id: 3, metric: '平均响应时间(ms)', value: 390 }] },
        { resource: 'task_1035', metrics: [{ id: 1, metric: '唤醒成功率', value: 97.1 }, { id: 2, metric: '识别准确率', value: 96.9 }, { id: 3, metric: '平均响应时间(ms)', value: 402 }] },
        { resource: 'task_1042', metrics: [{ id: 1, metric: '唤醒成功率', value: 95.8 }, { id: 2, metric: '识别准确率', value: 93.8 }, { id: 3, metric: '平均响应时间(ms)', value: 412 }] },
      ],
      case_categories: [],
      all_case_tags: [],
      all_metrics: ['唤醒成功率', '识别准确率', '平均响应时间(ms)'],
      device_stats: [],
      api_stats: [],
      devices: [],
      apis: [],
    },
    created_at: isSecondary ? '2026-10-15T11:30:00' : '2026-10-15T10:02:00',
    updated_at: isSecondary ? '2026-10-15T11:30:00' : '2026-10-15T10:02:00',
  }
}

/** 具体用例列表 mock（POST /reports/{id}/cases/search 形态；1201 详情页展示） */
const MOCK_REPORT_CASES: ReportCaseItem[] = [
  {
    id: 'c-1042-001',
    name: '远场唤醒-客厅 3 米',
    category: 'grp-farfield',
    tags: ['远场', '唤醒'],
    overall_status: 'pass',
    description: '客厅 3 米距离，环境噪声 35dB，测试两次唤醒词响应。',
    metrics: [
      { id: 1, metric: '唤醒成功率', value: 100, decimal_places: 1 },
      { id: 2, metric: '识别准确率', value: 96.8, decimal_places: 1 },
      { id: 3, metric: '平均响应时间(ms)', value: 418, decimal_places: 0 },
    ],
    audios: [
      { audio_id: 'a-9001', audio_name: '唤醒词-远场-客厅.wav', audio_type: 'wakeword', spl: 55, play_order: 1, noise_spl: 35, device_name: '智能音箱-旗舰-01' },
    ],
    asr: {
      reference: '小爱同学，今天天气怎么样？',
      results: {
        '智能音箱-旗舰-01': '小爱同学，今天天气怎么样？',
        'asr-streaming-v3': '小爱同学，今天天气怎么样？',
        'wakeword-detect-v2': '小爱同学，今天天气怎么样？',
      },
    },
    translation: undefined,
    logs: '[2026-10-15 08:42:01] 唤醒词检测命中\n[2026-10-15 08:42:01] ASR 请求 -> asr-streaming-v3\n[2026-10-15 08:42:02] ASR 响应 418ms\n[2026-10-15 08:42:02] 文本匹配成功 (相似度 0.98)',
  },
  {
    id: 'c-1042-002',
    name: '噪声场景-厨房设备运行',
    category: 'grp-noise',
    tags: ['噪声', '唤醒'],
    overall_status: 'fail',
    description: '厨房设备运行噪声 60dB，测试唤醒词误唤醒与识别。',
    metrics: [
      { id: 1, metric: '唤醒成功率', value: 66.7, decimal_places: 1 },
      { id: 2, metric: '识别准确率', value: 78.2, decimal_places: 1 },
      { id: 3, metric: '平均响应时间(ms)', value: 536, decimal_places: 0 },
    ],
    audios: [
      { audio_id: 'a-9002', audio_name: '唤醒词-噪声-厨房.wav', audio_type: 'wakeword', spl: 58, play_order: 1, noise_spl: 60, device_name: '智能音箱-旗舰-01' },
    ],
    asr: {
      reference: '小爱同学，播放一首歌',
      results: {
        '智能音箱-旗舰-01': '小爱同学，播放一首歌',
        'asr-streaming-v3': '小爱同学，播放一首歌',
        'wakeword-detect-v2': '小爱同学，播放一首（超时）',
      },
    },
    translation: undefined,
    logs: '[2026-10-15 08:50:11] 唤醒词检测命中\n[2026-10-15 08:50:12] ASR 响应 536ms\n[2026-10-15 08:50:12] wakeword-detect-v2 转写超时，降级重试',
  },
  {
    id: 'c-1042-003',
    name: '近场唤醒-桌面 0.5 米',
    category: 'grp-wakeup',
    tags: ['近场', '唤醒'],
    overall_status: 'pass',
    description: '桌面 0.5 米，安静环境，唤醒词连续三次。',
    metrics: [
      { id: 1, metric: '唤醒成功率', value: 100, decimal_places: 1 },
      { id: 2, metric: '识别准确率', value: 98.2, decimal_places: 1 },
      { id: 3, metric: '平均响应时间(ms)', value: 212, decimal_places: 0 },
    ],
    audios: [
      { audio_id: 'a-9003', audio_name: '唤醒词-近场-桌面.wav', audio_type: 'wakeword', spl: 62, play_order: 1, noise_spl: 30, device_name: '智能音箱-旗舰-02' },
    ],
    asr: {
      reference: '小爱同学，明天早上叫我起床',
      results: {
        '智能音箱-旗舰-02': '小爱同学，明天早上叫我起床',
        'asr-streaming-v3': '小爱同学，明天早上叫我起床',
      },
    },
    translation: undefined,
    logs: '[2026-10-15 08:58:31] 唤醒词检测命中\n[2026-10-15 08:58:31] ASR 响应 212ms',
  },
  {
    id: 'c-1042-004',
    name: '方言识别-粤语日常指令',
    category: 'grp-wakeup',
    tags: ['方言', '近场'],
    overall_status: 'pass',
    description: '粤语日常指令识别，安静环境。',
    metrics: [
      { id: 1, metric: '唤醒成功率', value: 100, decimal_places: 1 },
      { id: 2, metric: '识别准确率', value: 91.5, decimal_places: 1 },
    ],
    audios: [],
    asr: {
      reference: '帮我睇下听日天气',
      results: {
        '智能音箱-旗舰-01': '帮我睇下听日天气',
        'asr-streaming-v3': '帮我睇下听日天气',
      },
    },
    translation: { reference: '帮我看看明天天气', direction: '粤语 → 普通话', results: { '智能音箱-旗舰-01': '帮我看看明天天气' } },
    logs: '[2026-10-15 09:02:01] ASR 请求 -> asr-streaming-v3\n[2026-10-15 09:02:02] 翻译链路启用 粤语→普通话',
  },
  {
    id: 'c-1042-005',
    name: '误触测试-连续播报中唤醒',
    category: 'grp-noise',
    tags: ['噪声', '唤醒'],
    overall_status: 'skip',
    description: '播报持续中唤醒词误触，本轮跳过（人工复核）。',
    metrics: [],
    audios: [],
    asr: undefined,
    translation: undefined,
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
