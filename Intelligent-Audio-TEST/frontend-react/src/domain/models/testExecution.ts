/**
 * 测试执行流程领域模型（domain 层；10_测试执行.md §9 落位）。
 * 覆盖：执行参数（§3.6.3 四类）、任务创建/启动载荷（对照 task_bp.py POST /tasks +
 * POST /tasks/{id}/start）、Realtime frame 事件（§3.7，API测试功能设计文档 §5.3）、
 * 用例执行详情（§5.2 多轮指标对比/日志分页）。
 */

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
   * filter-all 圈定用当前筛选条件（关键字/分组/标签/评估维度/算法；camelCase，
   * 与 infrastructure TestCaseFilter 同构——随启动流程由 case-selection store 传入，
   * createTask 经 toTestCaseQuery 转 snake_case 调 POST /testcases/ids 全量圈定）。
   */
  caseFilter?: {
    keyword?: string
    groupId?: string | null
    tags?: string[]
    dimensionId?: number | null
    type?: 'e2e' | 'api' | null
    algorithmType?: string | null
  }
  /** 所选设备 id 集（设备+API 混合执行） */
  deviceIds: number[]
  /** 所选 API id 集（设备+API 混合执行） */
  apiIds: number[]
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

/** 用例执行结果（§5.2 设备×维度对比；preparedComparisonData 口径平移） */
export interface CaseMetricPoint {
  dimension: string
  /** 多轮时维度列带轮次后缀 @round:{n} / @overall */
  round?: number
  value: string
}

export interface CaseDeviceResult {
  deviceId: number
  deviceName: string
  status: 'pass' | 'fail'
  duration: number
  score: number | null
  metrics: CaseMetricPoint[]
  asrReference: string | null
  translationReference: string | null
  audioResults: Array<{ audioName: string; duration: number | null }>
}

/** 用例执行详情（GET /tasks/{taskId}/cases/{caseId}/detail + /results 平移） */
export interface CaseExecutionDetail {
  caseId: string
  taskId: number
  name: string
  executionStatus: string
  evaluationStatus: string
  duration: number
  score: number | null
  devices: CaseDeviceResult[]
}
