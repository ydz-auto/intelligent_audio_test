/**
 * Report Adapter —— DTO → Domain 子结构与实体转换
 *
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 * Enum 值不转换（type/status 保持后端原值），只转字段名。
 * 本文件导出的转换函数由 report.main.ts 组合使用，并经 reportAdapter.ts 转发为适配器导出面。
 */
import type {
  DetailedResult,
  ReportMetricConfig,
  ReportDeviceStat,
  ReportApiStat,
  ReportDeviceInfo,
  ReportApiInfo,
  ReportResourceHeader,
  ReportRawDataGroup,
  ReportMetricByResource,
  ReportTagMetricByResource,
  ReportCaseTypeStatRow,
  ReportCaseEntityDomain,
  ReportMetricStatsDomain,
  ReportRawDataEntityDomain,
  ReportAlgorithmResultItem,
  ReportReferenceParamEntry,
  ReportFieldMapping,
  ReportFieldMappingItem,
} from '../../domain/model/report'
import type {
  ReportMetricConfigDto,
  ReportDeviceStatDto,
  ReportApiStatDto,
  ReportDeviceInfoDto,
  ReportApiInfoDto,
  ReportResourceHeaderDto,
  ReportRawDataGroupDto,
  ReportMetricByResourceDto,
  ReportTagMetricByResourceDto,
  ReportCaseTypeStatRowDto,
  ReportDto,
} from '../dto/reportDto'
import { toSafeNumber as n } from './commonAdapter'
import { s } from './report.utils'

// ===== 摘要子结构转换 =====

export function toMetricConfig(raw: ReportMetricConfigDto): ReportMetricConfig {
  return {
    id: raw.id,
    name: raw.name,
    unit: raw.unit,
    decimalPlaces: raw.decimal_places,
    statisticMethod: raw.statistic_method,
    dimensionType: raw.dimension_type,
    parentDimensionId: raw.parent_dimension_id ?? null,
    parentDimensionName: raw.parent_dimension_name ?? null,
  }
}

/**
 * 用例维度明细。
 * 后端 detailed_results 历史键名混用（snake/camel 并存），此处对已知键双拼写兼容，
 * 其余未知键直接丢弃（禁止索引签名兜底）。
 */
export function toDetailedResult(raw: Record<string, unknown>): DetailedResult {
  const rec = raw as Record<string, unknown>
  const testCaseGroup = rec.test_case_group ?? rec.testCaseGroup
  const testCase = rec.test_case ?? rec.testCase
  const asr = rec.asr
  const translation = rec.translation
  const dimensionScores = rec.dimension_scores ?? rec.dimensionScores
  return {
    id: (rec.id ?? '') as string | number,
    caseName: s(rec.case_name ?? rec.caseName ?? ''),
    score: rec.score !== undefined && rec.score !== null ? n(rec.score) : undefined,
    result: rec.result !== undefined ? s(rec.result) : undefined,
    executionStatus: rec.execution_status !== undefined ? s(rec.execution_status) : undefined,
    testCaseId: (rec.test_case_id ?? rec.testCaseId) as string | number | undefined,
    testCaseName: rec.test_case_name !== undefined ? s(rec.test_case_name) : undefined,
    deviceName: rec.device_name !== undefined ? s(rec.device_name) : undefined,
    apiName: rec.api_name !== undefined ? s(rec.api_name) : undefined,
    audioName: rec.audio_name !== undefined ? s(rec.audio_name) : undefined,
    createdAt: rec.created_at !== undefined ? s(rec.created_at) : undefined,
    errorMessage: rec.error_message !== undefined ? s(rec.error_message) : undefined,
    // 嵌套对象：递归转换 snake_case 键
    testCaseGroup: testCaseGroup as DetailedResult['testCaseGroup'],
    testCaseTags: (rec.test_case_tags ?? rec.testCaseTags) as DetailedResult['testCaseTags'],
    testCase: testCase as DetailedResult['testCase'],
    device: rec.device as DetailedResult['device'],
    api: rec.api as DetailedResult['api'],
    asr: asr ? {
      referenceText: s((asr as Record<string, unknown>).reference_text ?? (asr as Record<string, unknown>).referenceText, undefined),
      resultText: (asr as Record<string, unknown>).result_text !== undefined ? s((asr as Record<string, unknown>).result_text) : (asr as Record<string, unknown>).resultText !== undefined ? s((asr as Record<string, unknown>).resultText) : undefined,
    } : undefined,
    translation: translation ? {
      referenceText: s((translation as Record<string, unknown>).reference_text ?? (translation as Record<string, unknown>).referenceText, undefined),
      resultText: (translation as Record<string, unknown>).result_text !== undefined ? s((translation as Record<string, unknown>).result_text) : (translation as Record<string, unknown>).resultText !== undefined ? s((translation as Record<string, unknown>).resultText) : undefined,
    } : undefined,
    dimensionScores: Array.isArray(dimensionScores)
      ? (dimensionScores as Array<Record<string, unknown>>).map(d => ({
          dimensionName: s(d.dimension_name ?? d.dimensionName ?? ''),
          score: n(d.score),
        }))
      : undefined,
    metrics: rec.metrics as Record<string, unknown> | undefined,
    audios: rec.audios as unknown[] | undefined,
    description: rec.description !== undefined ? s(rec.description) : undefined,
    logs: rec.logs !== undefined ? s(rec.logs) : undefined,
    testCaseType: rec.test_case_type !== undefined ? s(rec.test_case_type) : undefined,
    audioFilePath: rec.audio_file_path !== undefined ? s(rec.audio_file_path) : undefined,
    audioDuration: rec.audio_duration !== undefined ? n(rec.audio_duration) : undefined,
    audioId: rec.audio_id as string | number | undefined,
  }
}

export function toDeviceStat(raw: ReportDeviceStatDto): ReportDeviceStat {
  return {
    id: raw.id,
    name: raw.name,
    model: raw.model ?? undefined,
    type: raw.type ?? undefined,
    system: raw.system ?? undefined,
    systemVersion: raw.system_version ?? undefined,
    status: raw.status ?? undefined,
    metrics: raw.metrics ?? null,
    totalCases: n(raw.total_cases),
    completedCases: n(raw.completed_cases),
    failedCases: n(raw.failed_cases),
    successRate: n(raw.success_rate),
  }
}

export function toApiStat(raw: ReportApiStatDto): ReportApiStat {
  return {
    id: raw.id,
    name: raw.name,
    status: raw.status ?? undefined,
    maxProcess: raw.max_process ?? null,
    healthScore: raw.health_score ?? null,
    metrics: raw.metrics ?? null,
    totalCases: n(raw.total_cases),
    completedCases: n(raw.completed_cases),
    failedCases: n(raw.failed_cases),
    successRate: n(raw.success_rate),
    avgResponseTime: raw.avg_response_time ?? null,
    stability: raw.stability ?? null,
  }
}

export function toDeviceInfo(raw: ReportDeviceInfoDto): ReportDeviceInfo {
  return {
    id: raw.id,
    name: raw.name,
    model: raw.model ?? undefined,
    description: raw.description ?? undefined,
    type: raw.type ?? undefined,
    system: raw.system ?? undefined,
    systemVersion: raw.system_version ?? undefined,
    appName: raw.app_name ?? undefined,
    appVersion: raw.app_version ?? undefined,
    location: raw.location ?? undefined,
    maxAudioDuration: raw.max_audio_duration ?? null,
    needsPromptAudio: raw.needs_prompt_audio ?? null,
    connectionType: raw.connection_type ?? undefined,
    keywords: raw.keywords ?? undefined,
    serialNumber: raw.serial_number ?? undefined,
    ip: raw.ip ?? undefined,
    status: raw.status ?? undefined,
    lastOnlineAt: raw.last_online_at ?? null,
    createdAt: raw.created_at ?? null,
    updatedAt: raw.updated_at ?? null,
  }
}

export function toApiInfo(raw: ReportApiInfoDto): ReportApiInfo {
  return {
    id: raw.id,
    name: raw.name,
    vendor: raw.vendor ?? undefined,
    apiUrl: raw.api_url ?? undefined,
    description: raw.description ?? undefined,
    status: raw.status ?? undefined,
    maxProcess: raw.max_process ?? null,
    maxTimeout: raw.max_timeout ?? null,
    maxAudioDuration: raw.max_audio_duration ?? null,
    healthScore: raw.health_score ?? null,
    createdAt: raw.created_at ?? null,
    updatedAt: raw.updated_at ?? null,
  }
}

export function toResourceHeader(raw: ReportResourceHeaderDto): ReportResourceHeader {
  return {
    key: raw.key,
    label: raw.label,
    type: raw.type ?? undefined,
    id: raw.id ?? null,
    name: raw.name ?? null,
    version: raw.version ?? null,
    editable: raw.editable ?? null,
  }
}

export function toRawDataGroup(raw: ReportRawDataGroupDto): ReportRawDataGroup {
  return {
    resource: raw.resource,
    metrics: (raw.metrics ?? []).map(m => ({ metric: m.metric, values: m.values ?? [] })),
  }
}

export function toMetricByResource(raw: ReportMetricByResourceDto): ReportMetricByResource {
  return {
    resource: raw.resource,
    categories: (raw.categories ?? []).map(c => ({
      categoryId: c.category_id,
      categoryName: c.category_name,
      metrics: (c.metrics ?? []).map(m => ({
        id: m.id ?? null,
        metric: m.metric,
        value: n(m.value),
      })),
    })),
    // 扁平行（resource 级别全局平均）透传，供分类对比卡按已知分组复制解析
    metrics: (raw.metrics ?? []).map(m => ({
      id: m.id ?? null,
      metric: m.metric,
      value: n(m.value),
    })),
  }
}

export function toTagMetricByResource(raw: ReportTagMetricByResourceDto): ReportTagMetricByResource {
  return {
    resource: raw.resource,
    tags: (raw.tags ?? []).map(t => ({
      tagId: t.tag_id,
      tagName: t.tag_name,
      categoryId: t.category_id ?? null,
      categoryName: t.category_name ?? null,
      metrics: (t.metrics ?? []).map(m => ({
        id: m.id ?? null,
        metric: m.metric,
        value: n(m.value),
      })),
    })),
  }
}

export function toCaseTypeStatRow(raw: ReportCaseTypeStatRowDto): ReportCaseTypeStatRow {
  return {
    groupId: raw.group_id,
    groupName: raw.group_name,
    metrics: (raw.metrics ?? []).map(m => ({
      id: m.id ?? null,
      metric: m.metric,
      value: n(m.value),
    })),
  }
}

// ===== 聚合根子实体转换 =====

export function toCaseEntity(raw: NonNullable<ReportDto['cases']>[number]): ReportCaseEntityDomain {
  return {
    id: raw.id,
    reportId: raw.report_id,
    testCaseId: raw.test_case_id,
    resultSummary: raw.result_summary ?? {},
    score: raw.score ?? null,
  }
}

export function toMetricStat(raw: NonNullable<ReportDto['metric_stats']>[number]): ReportMetricStatsDomain {
  return {
    id: raw.id,
    reportId: raw.report_id,
    metricName: raw.metric_name,
    avg: n(raw.avg),
    min: n(raw.min),
    max: n(raw.max),
    stdDev: n(raw.std_dev),
    sampleCount: n(raw.sample_count),
  }
}

export function toRawDataEntity(raw: NonNullable<ReportDto['raw_data']>[number]): ReportRawDataEntityDomain {
  return {
    id: raw.id,
    reportId: raw.report_id,
    dataType: raw.data_type,
    data: raw.data ?? {},
  }
}

/**
 * 算法结果项（algorithm_results[] 元素 → camelCase）。
 * value 载荷为数据驱动结构（多轮 aggregated/output 指标名、时间轴分段等为后端数据 key），原样保留。
 */
export function toAlgorithmResultItem(raw: Record<string, unknown>): ReportAlgorithmResultItem {
  return {
    paramCode: s(raw.param_code ?? raw.paramCode ?? ''),
    paramType: s(raw.param_type ?? raw.paramType ?? ''),
    roundNumber: raw.round_number !== undefined
      ? n(raw.round_number)
      : raw.roundNumber !== undefined ? n(raw.roundNumber) : undefined,
    dimensionName: raw.dimension_name !== undefined
      ? s(raw.dimension_name)
      : raw.dimensionName !== undefined ? s(raw.dimensionName) : null,
    label: raw.label !== undefined ? s(raw.label) : undefined,
    device: raw.device !== undefined ? s(raw.device) : undefined,
    value: raw.value === null || raw.value === undefined
      ? undefined
      : (typeof raw.value === 'string' || typeof raw.value === 'number' || typeof raw.value === 'boolean')
        ? raw.value
        : raw.value as Record<string, unknown> | unknown[],
  }
}

/** 参考参数条目（reference_params 字典值元素 → camelCase；字典键为参数 code 数据 key，由调用方保留） */
export function toReferenceParamEntry(raw: Record<string, unknown>): ReportReferenceParamEntry {
  return {
    code: raw.code !== undefined ? s(raw.code) : undefined,
    type: raw.type !== undefined ? s(raw.type) : undefined,
    value: raw.value,
    label: raw.label !== undefined ? s(raw.label) : undefined,
    roundNumber: raw.round_number !== undefined
      ? n(raw.round_number)
      : raw.roundNumber !== undefined ? n(raw.roundNumber) : undefined,
    segments: Array.isArray(raw.segments) ? raw.segments as unknown[] : undefined,
    text: raw.text !== undefined ? s(raw.text) : undefined,
    json: raw.json !== undefined ? s(raw.json) : undefined,
    annotationCode: raw.annotation_code !== undefined ? s(raw.annotation_code) : raw.annotationCode !== undefined ? s(raw.annotationCode) : undefined,
    annotationFormat: raw.annotation_format !== undefined ? s(raw.annotation_format) : raw.annotationFormat !== undefined ? s(raw.annotationFormat) : undefined,
  }
}

// ===== 共享字典/快照结构转换（searchCases 与 task getCaseDetail 复用） =====

/**
 * 参考参数字典（reference_params → camelCase）。
 * 字典键为参数 code 数据 key（可能含 @round:N 后缀），原样保留；
 * 值为对象时逐条转 ReportReferenceParamEntry，非对象值原样保留。
 */
export function toReferenceParamsDict(raw: unknown): Record<string, ReportReferenceParamEntry | unknown> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const result: Record<string, ReportReferenceParamEntry | unknown> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    result[key] = value !== null && typeof value === 'object' && !Array.isArray(value)
      ? toReferenceParamEntry(value as Record<string, unknown>)
      : value
  }
  return result
}

/** 算法字段映射项（field_mapping result/reference 数组元素 → camelCase） */
export function toFieldMappingItem(raw: Record<string, unknown>): ReportFieldMappingItem {
  return {
    paramCode: raw.param_code !== undefined
      ? s(raw.param_code)
      : raw.paramCode !== undefined ? s(raw.paramCode) : undefined,
    paramType: raw.param_type !== undefined
      ? s(raw.param_type)
      : raw.paramType !== undefined ? s(raw.paramType) : undefined,
    label: raw.label !== undefined ? s(raw.label) : undefined,
    roundNumber: raw.round_number !== undefined
      ? n(raw.round_number)
      : raw.roundNumber !== undefined ? n(raw.roundNumber) : null,
    dimensionName: raw.dimension_name !== undefined
      ? s(raw.dimension_name)
      : raw.dimensionName !== undefined ? s(raw.dimensionName) : null,
    value: raw.value !== undefined ? s(raw.value) : undefined,
    device: raw.device !== undefined ? s(raw.device) : undefined,
  }
}

/** 算法字段映射快照（{algorithm_type: {result, reference}} → camelCase；algorithm_type 键为数据 key，保留原样） */
export function toFieldMappings(raw: unknown): Record<string, ReportFieldMapping> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const result: Record<string, ReportFieldMapping> = {}
  for (const [algoType, mapping] of Object.entries(raw as Record<string, unknown>)) {
    if (!mapping || typeof mapping !== 'object' || Array.isArray(mapping)) continue
    const m = mapping as Record<string, unknown>
    const toItems = (v: unknown): ReportFieldMappingItem[] =>
      Array.isArray(v) ? (v as Array<Record<string, unknown>>).map(toFieldMappingItem) : []
    result[algoType] = {
      result: toItems(m.result),
      reference: toItems(m.reference),
    }
  }
  return result
}