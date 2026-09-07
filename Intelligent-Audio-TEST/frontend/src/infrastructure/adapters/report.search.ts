/**
 * Report Adapter —— searchCases 响应转换
 *
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 * 本层为唯一知道 snake_case 的层，嵌套 snake_case 字段在此统一转 camelCase。
 */
import { toSafeNumber as n } from './commonAdapter'
import { s } from './report.utils'
import type { ReportReferenceParamEntry } from '../../domain/model/report'
import { toAlgorithmResultItem, toReferenceParamEntry, toReferenceParamsDict } from './report.mapping'

// ===== searchCases 响应转换 =====

/** searchCases 返回的单条用例（snake_case → camelCase） */
export function toSearchCaseItem(raw: Record<string, unknown>): Record<string, unknown> {
  const rec = raw
  const asr = rec.asr
  const translation = rec.translation
  const dimensionScores = rec.dimension_scores ?? rec.dimensionScores
  const algoResults = rec.algorithm_results ?? rec.algorithmResults
  const refParams = rec.reference_params ?? rec.referenceParams
  const result: Record<string, unknown> = {
    id: rec.id,
    name: s(rec.name ?? rec.case_name ?? rec.caseName ?? ''),
    category: rec.category ?? s(rec.test_case_type ?? rec.testCaseType ?? ''),
    description: rec.description !== undefined ? s(rec.description) : undefined,
    tags: rec.tags ?? rec.test_case_tags ?? rec.testCaseTags ?? [],
    metrics: rec.metrics ?? {},
    results: rec.results ?? [],
    audios: rec.audios ?? [],
    logs: rec.logs !== undefined ? s(rec.logs) : '',
    algorithmType: s(rec.algorithm_type ?? rec.algorithmType ?? ''),
    algorithmResults: Array.isArray(algoResults)
      ? (algoResults as Array<Record<string, unknown>>).map(toAlgorithmResultItem)
      : [],
    referenceParams: toReferenceParamsDict(refParams),
    // 嵌套 asr/translation 块的 snake_case → camelCase
    asr: asr ? {
      referenceText: s((asr as Record<string, unknown>).reference_text ?? (asr as Record<string, unknown>).referenceText, undefined),
      resultText: (asr as Record<string, unknown>).result_text !== undefined ? s((asr as Record<string, unknown>).result_text) : (asr as Record<string, unknown>).resultText !== undefined ? s((asr as Record<string, unknown>).resultText) : undefined,
      results: (asr as Record<string, unknown>).results,
    } : undefined,
    translation: translation ? {
      referenceText: s((translation as Record<string, unknown>).reference_text ?? (translation as Record<string, unknown>).referenceText, undefined),
      resultText: (translation as Record<string, unknown>).result_text !== undefined ? s((translation as Record<string, unknown>).result_text) : (translation as Record<string, unknown>).resultText !== undefined ? s((translation as Record<string, unknown>).resultText) : undefined,
      results: (translation as Record<string, unknown>).results,
    } : undefined,
    // 时间轴数据键（后端遗留 snake_case，统一转 camelCase）
    rttmRes: rec.rttm_res ?? rec.rttmRes,
    stmRes: rec.stm_res ?? rec.stmRes,
    rttmRef: rec.rttm_ref ?? rec.rttmRef,
    stmRef: rec.stm_ref ?? rec.stmRef,
    rttmHyp: rec.rttm_hyp ?? rec.rttmHyp,
    stmHyp: rec.stm_hyp ?? rec.stmHyp,
    // detailed_results 中的嵌套字段
    testCaseId: rec.test_case_id ?? rec.testCaseId,
    testCaseName: rec.test_case_name !== undefined ? s(rec.test_case_name) : rec.testCaseName !== undefined ? s(rec.testCaseName) : undefined,
    testCaseGroup: rec.test_case_group ?? rec.testCaseGroup,
    device: rec.device,
    api: rec.api,
    dimensionScores: Array.isArray(dimensionScores)
      ? (dimensionScores as Array<Record<string, unknown>>).map(d => ({
          dimensionName: s(d.dimension_name ?? d.dimensionName ?? ''),
          score: n(d.score),
        }))
      : undefined,
    status: rec.status,
    createdAt: rec.created_at !== undefined ? s(rec.created_at) : rec.createdAt,
    audioList: rec.audio_list ?? rec.audioList,
  }
  // 过滤 undefined 值
  for (const key of Object.keys(result)) {
    if (result[key] === undefined) delete result[key]
  }
  return result
}

/** searchCases 分页响应（snake_case → camelCase） */
export function toSearchCaseResult(dto: unknown): { items: Record<string, unknown>[]; total: number } {
  const raw = dto as Record<string, unknown> | null
  if (!raw) return { items: [], total: 0 }
  // 兼容两种响应形状：{items, total} 或 {data: {items, total}}
  const inner = (raw.items !== undefined ? raw : (raw.data as Record<string, unknown> | undefined)) ?? {}
  const itemsRaw = inner.items
  const items = Array.isArray(itemsRaw)
    ? (itemsRaw as Array<Record<string, unknown>>).map(toSearchCaseItem)
    : []
  return {
    items,
    total: n(inner.total, items.length),
  }
}