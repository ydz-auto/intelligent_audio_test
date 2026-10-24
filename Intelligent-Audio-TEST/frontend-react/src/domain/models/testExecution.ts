/**
 * 测试执行流程领域模型（domain 层；10_测试执行.md §9 落位）。
 * 覆盖：执行参数（§3.6.3 四类）、任务创建/启动载荷（对照 task_bp.py POST /tasks +
 * POST /tasks/{id}/start）、Realtime frame 事件（§3.7，API测试功能设计文档 §5.3）、
 * 用例执行详情（§5.2 多轮指标对比/日志分页）。
 */

import type { DeviceType } from './device'
import type { CaseResultForReview } from './review'

/** 目标类型（INT-1115 target_modes.target_type 枚举） */
export type TargetType = 'device' | 'api'

/** 执行模式（INT-1115：每目标并行/串行；缺省=并行） */
export type ExecutionMode = 'parallel' | 'serial'

/** 逐目标执行模式（INT-1115 契约；列表顺序=选中顺序=串行链顺序） */
export interface TargetMode {
  targetType: TargetType
  targetId: number
  mode: ExecutionMode
}

/** 逐目标设备类型分配（INT-1433；device_type 三值——websocket_api Realtime 路由前置 + API/设备混跑）。
 * 每个选中目标一条（物理设备 / HTTP API / WebSocket API）；createTask 按「所选用例 × 选中目标」
 * 展开为后端 case_devices（TaskCaseDeviceAssignment 契约），后端按 (case_id, device_type, device_id)
 * 落多条 TaskCase——同一用例在多个目标间执行成立。 */
export interface TargetDeviceAssignment {
  deviceType: DeviceType
  /** 目标 id 字符串化（后端 device_id 契约为 str；物理设备/API 均取自身 id） */
  deviceId: string
}

/** 执行参数（§3.6.3；INT-486 2026-10-16 口径：设备+API 混合执行，均可编辑） */
export interface ExecutionParams {
  /** 测试轮数（min 1 max 20，default 1） */
  rounds: number
  /** 单轮次超时上限（秒，default 60） */
  timeout: number
  /** 失败自动重试次数（min 0 max 5，default 0） */
  retries: number
  /** 并发任务数（default 4；API 并发上限自动合计作补充展示） */
  concurrency: number
  /** 网络环境（默认/Wi-Fi/移动网络/飞行模式；device:control 才可设） */
  network: string
  /** 报告模板（默认标准模板） */
  reportTemplate: string
  /** 报告包含内容（图表/详细日志/参考参数，默认全勾） */
  includeCharts: boolean
  includeDetailedLogs: boolean
  includeReferenceParams: boolean
  /** 导出格式预选（CSV/Excel/PDF/HTML，对齐 15_报告域 §4.3） */
  exportFormats: string[]
}

export const DEFAULT_EXECUTION_PARAMS: ExecutionParams = {
  rounds: 1,
  timeout: 60,
  retries: 0,
  concurrency: 4,
  network: '默认',
  reportTemplate: '标准模板',
  includeCharts: true,
  includeDetailedLogs: true,
  includeReferenceParams: true,
  exportFormats: ['html'],
}

/**
 * filter-all 圈定条件（INT-1544：步骤一页面筛选与任务启动同源）。
 * 键与 POST /testcases/ids 契约一致（task_service fetch_case_ids）：
 * search = 关键字（该端点不认 keyword）、group = 分组**名**（不认 group_id，INT-1267）、
 * tag = 标签名 / dimensionId / algorithmType 同列表筛选项。
 * 注意：收藏/回收站是列表视图开关，不是圈定条件（ids 端点无 favorite 键）。
 */
export interface CaseSelectionFilter {
  search?: string
  group?: string | null
  tag?: string | null
  dimensionId?: number | null
  algorithmType?: string | null
}

/** 任务创建/启动载荷（task_bp.py POST /tasks + POST /tasks/{id}/start；TODO 接线） */
export interface TaskLaunchInput {
  name: string
  /** 用例不分类型（INT-486 2026-10-16 口径；test_type 残留列待 INT-79 废弃） */
  testType: 'e2e' | 'api' | null
  algorithmType: string | null
  testCaseIds: string[]
  /** 圈定模式：未手动选择时按筛选条件全量圈定（filter-all 口径显性化） */
  filterAllMode: boolean
  /**
   * filter-all 圈定用当前筛选条件（INT-1544：case-selection store 由步骤一持续同步，
   * 与列表「全部 N 条用例」同源；createTask 经 POST /testcases/ids 全量圈定）。
   */
  caseFilter?: CaseSelectionFilter
  /** 所选设备 id 集（设备+API 混合执行） */
  deviceIds: number[]
  /** 所选 API id 集（设备+API 混合执行） */
  apiIds: number[]
  /**
   * 逐目标执行模式（INT-1115 契约 2026-10-21；列表顺序=选中顺序=串行链顺序，
   * 恰好覆盖全部选中目标一次；缺省/空数组=全目标并行）。废弃全局 execution_mode/serial_first。
   */
  targetModes: TargetMode[]
  /**
   * 逐目标设备类型分配（INT-1433 2026-10-23；websocket_api Realtime 路由前置）：
   * 每个选中目标一条；createTask 按解析后的用例集（filter-all/手动）展开为
   * case_devices。空数组/缺省 = 不携带（旧派生口径，零回归）。
   */
  targetDeviceAssignments: TargetDeviceAssignment[]
  params: ExecutionParams
}

/** Realtime frame 事件类型（§3.7；snake_case 原始值经 frameEventAdapter 转 camelCase 消费） */
export type RealtimeFrameKind =
  | 'text_delta'
  | 'audio_delta'
  | 'speech_started'
  | 'speech_ended'
  | 'round_started'
  | 'round_completed'

/** Realtime frame 事件（Presentation 层消费形态，camelCase） */
export interface RealtimeFrame {
  caseId: string
  kind: RealtimeFrameKind
  /** 文字流增量（ai_text_delta） */
  textDelta?: string
  /** 音频进度 0-100（ai_audio_delta 累积） */
  audioProgress?: number
  round?: number
  timestamp: string
}

/** 用例执行结果（§5.2 设备×维度；preparedComparisonData 口径平移） */
export interface CaseMetricPoint {
  dimension: string
  /** 轮次（1 起）；整体评估（round_number null）为 undefined */
  round?: number
  value: string
}

/** 评估维度配置（detail metric_configs；指标行顺序权威源） */
export interface CaseMetricConfig {
  code: string
  name: string
}

/** 指标行（行=指标、列=设备；V9.7.10 currentRoundTableData 同口径） */
export interface CaseMetricRow {
  /** 指标（评估维度）名，行头展示 */
  dimension: string
  /** 设备名 → 显示值（该设备本轮无此维度时缺省 → 渲染「—」） */
  values: Record<string, string>
}

/**
 * 轮次 Tab（V9.7.10 TestCaseReportDetail roundTabs / currentRoundTableData 同口径）：
 * 有轮次标记 → 「第1轮…第N轮」+「整体」（整体有评估数据才出现）；
 * 无任何轮次标记 → 单个「指标」Tab（不渲染 Tab 栏）。
 * `@round:{n}` / `@overall` 只是数据侧内部键，不得作为列头展示（INT-1723 规范回写）。
 */
export interface CaseRoundTab {
  /** `round:{n}` / `overall` / `all` */
  key: string
  /** 展示文案：第N轮 / 整体 / 指标 */
  label: string
  /** 轮次（1 起）；整体与单轮「指标」Tab 为 null */
  round: number | null
  kind: 'round' | 'overall' | 'all'
  /** 本 Tab 的指标行（行=指标，列=设备；无值维度不出行） */
  rows: CaseMetricRow[]
}

/** 结果音频（可试听）：url 为后端直出地址，path 为静态相对路径（播放前经 stream-by-path 换预签名 URL） */
export interface CaseAudioResult {
  /** 展示名（filename / param_code / 「音频N」） */
  audioName: string
  deviceName: string | null
  /** 音频库 id（参考音频 audio_list 有；结果音频一般为 null） */
  audioId?: number | null
  /** 所属轮次（1 起；无轮次信息为 null → 所有轮次 Tab 下都展示） */
  round?: number | null
  url: string | null
  path: string | null
}

/**
 * 执行结果音频字段（detail algorithm_results 里 `param_type=audio_file` 的项）。
 * V9.7.10 把这类项当作**结果字段**（TestCaseReportDetail.vue:246/:297 播放钮、:834-891 按 Tab
 * 过滤），与 `result_audios` 的「结果音频」块不是一回事：后者按设备分组、任何 Tab 都显示全部。
 */
export interface CaseResultAudioField {
  /** 原始 param_code（如 `user_wav@round:1`） */
  paramCode: string
  /** 展示名：原始参数名去掉 `@round:N` / `@overall` 内部后缀（内部键不进 UI） */
  label: string
  /** 轮次（1 起）；整体评估字段与无轮次标记字段为 null */
  round: number | null
  /** param_code 以 `@overall` 结尾（整体评估字段） */
  overall: boolean
  /** 所属评估维度（整体 Tab 下用于区分「有维度归属」与「设备/API 执行结果」） */
  dimensionName: string | null
  deviceName: string | null
  url: string | null
  path: string
}

/** 设备结果行（detail devices 设备名 + /results 结果行维度组合；10 §5.2） */
export interface CaseDeviceResult {
  /** /results 结果行 id（无执行结果时为 null） */
  resultId: number | null
  deviceId: number | null
  deviceName: string
  /** 结果行执行状态（completed/failed/stopped/skipped；无结果行为 null → 显示「—」） */
  executionStatus: string | null
  metrics: CaseMetricPoint[]
  asrReference: string | null
  translationReference: string | null
}

/** 用例执行详情·算法结果扁平项（GET /tasks/{taskId}/cases/{caseId}/detail algorithm_results 实测；
 * API/voice_llm 用例（devices 空）分节①结果摘要消费；对照 report 域 ReportAlgorithmResult 同构） */
export interface CaseAlgorithmResult {
  paramCode: string
  paramType?: string
  label?: string
  roundNumber?: number
  dimensionName?: string
  device?: string
  value?: unknown
  rounds?: unknown
}

/** 用例执行详情（GET /tasks/{taskId}/cases/{caseId}/detail + /results 平移） */
export interface CaseExecutionDetail {
  caseId: string
  taskId: number
  name: string
  executionStatus: string
  evaluationStatus: string
  /** 执行耗时（秒；后端缺省 null → 头部不渲染「耗时」，旧 Vue 同口径） */
  duration: number | null
  score: number | null
  algorithmType: string | null
  algorithmResults: CaseAlgorithmResult[]
  /** 评估维度配置（指标行顺序权威源；后端 metric_configs） */
  metricConfigs: CaseMetricConfig[]
  /** 轮次 Tab（第1轮…第N轮 + 整体；无轮次标记时单个「指标」Tab） */
  roundTabs: CaseRoundTab[]
  devices: CaseDeviceResult[]
  /** 结果音频（detail `result_audios`：按设备分组，任何轮次 Tab 都显示全部） */
  resultAudios: CaseAudioResult[]
  /** 执行结果音频字段（algorithm_results 的 audio_file 项；按当前轮次 Tab 过滤） */
  resultAudioFields: CaseResultAudioField[]
  /** 参考/输入音频（detail audio_list；旧 Vue 走「音频时间轴」） */
  referenceAudios: CaseAudioResult[]
  /** 执行结果行（/results；复核入口准入与人工复核弹窗消费） */
  results: CaseResultForReview[]
}
