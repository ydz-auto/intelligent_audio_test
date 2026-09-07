/**
 * 用例详情 ReadModel（getCaseDetail / getCaseResults 的 Domain 契约）
 * camelCase、零依赖、无索引签名兜底。
 * 注意：algorithmResults / referenceParams 的 value 载荷为数据驱动结构，
 * 多轮 aggregated/output 指标名、时间轴分段等为后端数据 key，原样保留。
 */
import type {
  ReportAlgorithmResultItem,
  ReportReferenceParamEntry,
  ReportFieldMapping,
  ReportMetricConfig,
} from './report'

/** 维度评估结果条目（results[].dimensions 元素） */
export interface CaseDimensionResult {
  id?: string | number
  name?: string
  value?: number | string
  score?: number
  roundNumber?: number | null
}

/** 设备/API 执行结果条目（getCaseResults results[] 元素） */
export interface CaseExecutionResult {
  id: string | number
  deviceId?: string | number
  deviceName?: string
  apiId?: string | number
  apiName?: string
  executionStatus?: string
  responseTime?: number | null
  algorithmResult?: unknown
  asrResult?: string | null
  translationResult?: string | null
  resultData?: unknown
  errorMessage?: string | null
  dimensions?: CaseDimensionResult[]
  createdAt?: string | null
}

/** 结果音频条目（result_audios 字典值数组元素） */
export interface CaseResultAudio {
  url?: string
  filename?: string
  paramCode?: string
}

/** 用例详情（getCaseDetail 响应 → camelCase） */
export interface CaseDetail {
  taskId: string
  caseId: string
  caseName: string
  status?: string
  executionStatus?: string
  evaluationStatus?: string
  startedAt?: string | null
  completedAt?: string | null
  duration?: number | null
  errorMessage?: string | null
  /** 参考音频列表（元素含 url/path/name 等展示字段，由音频归一化工具消费） */
  audioList: unknown[]
  /** 参考参数字典：键为参数 code 数据 key（可能含 @round:N 后缀，保留原样） */
  referenceParams: Record<string, ReportReferenceParamEntry | unknown>
  algorithmResults: ReportAlgorithmResultItem[]
  algorithmType: string
  /** 设备名列表 */
  devices: string[]
  metricConfigs: ReportMetricConfig[]
  fieldMapping: ReportFieldMapping
  /** 结果音频：设备名 → 音频条目数组 */
  resultAudios: Record<string, CaseResultAudio[]>
}

/** 用例结果集（getCaseResults 响应 → camelCase） */
export interface CaseResults {
  taskId?: string
  caseId?: string
  caseName?: string
  results: CaseExecutionResult[]
}
