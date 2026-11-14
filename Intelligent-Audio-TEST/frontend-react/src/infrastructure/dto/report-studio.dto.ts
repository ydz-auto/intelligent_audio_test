/**
 * Report Studio / 报告包 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照：
 *   GET  /api/v1/report-studio/documents        → { items[], total, limit, offset }（document 字段见
 *        report_service `_doc_dict`，列表不带 markdown_content）
 *   GET  /api/v1/report-studio/documents/{id}   → 同上单条 + markdown_content
 *   POST /api/v1/report-studio/import           → 新建文档（source_type=uploaded_file）
 *   POST /api/v1/data-transfer/report/import    → 导入回执（D6）
 * 页面层只读 domain/models/report-studio。
 */
import {
  StudioExportStatus,
  StudioSourceType,
  type ReportPackageImportReceipt,
  type ReportPackageManifestSummary,
  type StudioDocument,
  type StudioDocumentList,
  type StudioDocumentVersion,
  type StudioExportJob,
  type StudioExportStatusValue,
  type StudioSourceTypeValue,
} from '@/domain/models/report-studio'

/** GET /report-studio/documents 单项（snake_case） */
export interface StudioDocumentDto {
  doc_id: string
  report_id?: number | null
  title?: string
  current_version?: number
  etag?: string
  chart_refs?: string[]
  style_prefs?: Record<string, unknown>
  agent_session_id?: string | null
  created_by?: number | null
  created_at?: string | null
  updated_at?: string | null
  source_type?: string
  parent_doc_id?: string | null
  source_file_path?: string | null
  source_format?: string | null
  source_file_size?: number | null
  source_download_ref?: string | null
  markdown_content?: string
}

export interface StudioDocumentListDto {
  items?: StudioDocumentDto[]
  total?: number
  limit?: number
  offset?: number
}

/** POST /data-transfer/report/import 回执（D6 result.data） */
export interface ReportPackageImportReceiptDto {
  reportId?: number
  report_id?: number
  targetResolvedBy?: string
  target_resolved_by?: string
  batchId?: string
  batch_id?: string
  deletedCounts?: Record<string, number>
  deleted_counts?: Record<string, number>
  insertedCounts?: Record<string, number>
  inserted_counts?: Record<string, number>
  documentIdMapping?: Record<string, string>
  document_id_mapping?: Record<string, string>
  chartIdMapping?: Record<string, string>
  chart_id_mapping?: Record<string, string>
  agentSessionDropped?: number
  agent_session_dropped?: number
  warnings?: string[]
  rollbackAvailable?: boolean
  rollback_available?: boolean
}

/** 包内 manifest.json（报告包由 task_service 生成，字段为 camelCase） */
export interface ReportPackageManifestDto {
  kind?: string
  version?: string
  exportedAt?: string
  sourceTask?: {
    id?: number
    name?: string
    caseSetHash?: string
  }
  entities?: string[]
  docVersionScope?: string
  stats?: Record<string, number>
}

function toSourceType(value: string | undefined): StudioSourceTypeValue {
  switch (value) {
    case StudioSourceType.UPLOADED_FILE:
      return StudioSourceType.UPLOADED_FILE
    case StudioSourceType.AGENT_SUMMARY:
      return StudioSourceType.AGENT_SUMMARY
    case StudioSourceType.PLATFORM_REPORT:
      return StudioSourceType.PLATFORM_REPORT
    default:
      // 存量行默认 platform_report（迁移口径），未知值不阻断展示
      return StudioSourceType.PLATFORM_REPORT
  }
}

export function toStudioDocument(dto: StudioDocumentDto): StudioDocument {
  return {
    docId: dto.doc_id,
    reportId: dto.report_id ?? null,
    title: dto.title ?? '',
    markdownContent: dto.markdown_content ?? '',
    currentVersion: dto.current_version ?? 1,
    etag: dto.etag ?? '',
    chartRefs: Array.isArray(dto.chart_refs) ? dto.chart_refs : [],
    stylePrefs: dto.style_prefs ?? {},
    agentSessionId: dto.agent_session_id ?? null,
    parentDocId: dto.parent_doc_id ?? null,
    sourceType: toSourceType(dto.source_type),
    sourceFormat: dto.source_format ?? null,
    sourceFileSize: dto.source_file_size ?? null,
    sourceFilePath: dto.source_file_path ?? null,
    sourceDownloadRef: dto.source_download_ref ?? null,
    createdBy: dto.created_by ?? null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

export function toStudioDocumentList(
  dto: StudioDocumentListDto | null | undefined
): StudioDocumentList {
  const items = (dto?.items ?? []).map(toStudioDocument)
  return {
    items,
    total: dto?.total ?? items.length,
    limit: dto?.limit ?? items.length,
    offset: dto?.offset ?? 0,
  }
}

/** GET /report-studio/documents/{id}/versions 单项（snake_case） */
export interface StudioVersionDto {
  id?: number
  doc_id?: string
  version?: number
  markdown_content?: string
  parent_version?: number | null
  snapshot_reason?: string
  created_at?: string | null
  created_by?: number | null
}

export function toStudioDocumentVersion(
  dto: StudioVersionDto | null | undefined
): StudioDocumentVersion {
  return {
    id: dto?.id ?? 0,
    docId: dto?.doc_id ?? '',
    version: dto?.version ?? 0,
    // 后端快照列表不含正文（_version_dict），恒为空；历史正文只能恢复后读取
    markdownContent: dto?.markdown_content ?? '',
    parentVersion: dto?.parent_version ?? null,
    snapshotReason: dto?.snapshot_reason ?? '',
    createdAt: dto?.created_at ?? null,
    createdBy: dto?.created_by ?? null,
  }
}

export interface StudioVersionListDto {
  items?: StudioVersionDto[]
  total?: number
}

/** POST /documents/{id}/exports 与 GET /exports/{id}（snake_case） */
export interface StudioExportJobDto {
  export_id?: string
  doc_id?: string
  version?: number
  format?: string
  theme?: string
  status?: string
  progress?: number
  error?: string | null
  created_at?: string | null
  updated_at?: string | null
  download_ref?: string | null
}

const EXPORT_STATUSES: StudioExportStatusValue[] = [
  StudioExportStatus.PENDING,
  StudioExportStatus.RUNNING,
  StudioExportStatus.DONE,
  StudioExportStatus.FAILED,
]

/** 未知状态按失败处理（不让页面卡在轮询里），并回显原始值供排查 */
function toExportStatus(value: string | undefined): StudioExportStatusValue {
  const status = (value ?? '') as StudioExportStatusValue
  return EXPORT_STATUSES.includes(status) ? status : StudioExportStatus.FAILED
}

export function toStudioExportJob(
  dto: StudioExportJobDto | null | undefined
): StudioExportJob {
  return {
    exportId: dto?.export_id ?? '',
    docId: dto?.doc_id ?? '',
    version: dto?.version ?? 0,
    format: dto?.format ?? '',
    theme: dto?.theme ?? '',
    status: toExportStatus(dto?.status),
    progress: dto?.progress ?? 0,
    error: dto?.error ?? null,
    createdAt: dto?.created_at ?? null,
    updatedAt: dto?.updated_at ?? null,
    downloadRef: dto?.download_ref ?? null,
  }
}

function pickNumber(a: number | undefined, b: number | undefined): number {
  return a ?? b ?? 0
}

export function toReportPackageImportReceipt(
  dto: ReportPackageImportReceiptDto | null | undefined
): ReportPackageImportReceipt {
  return {
    reportId: dto?.reportId ?? dto?.report_id ?? null,
    targetResolvedBy: dto?.targetResolvedBy ?? dto?.target_resolved_by ?? null,
    batchId: dto?.batchId ?? dto?.batch_id ?? null,
    deletedCounts: dto?.deletedCounts ?? dto?.deleted_counts ?? {},
    insertedCounts: dto?.insertedCounts ?? dto?.inserted_counts ?? {},
    documentIdMapping: dto?.documentIdMapping ?? dto?.document_id_mapping ?? {},
    chartIdMapping: dto?.chartIdMapping ?? dto?.chart_id_mapping ?? {},
    agentSessionDropped: pickNumber(
      dto?.agentSessionDropped,
      dto?.agent_session_dropped
    ),
    warnings: dto?.warnings ?? [],
    rollbackAvailable: dto?.rollbackAvailable ?? dto?.rollback_available ?? false,
  }
}

export function toReportPackageManifest(
  dto: ReportPackageManifestDto | null | undefined
): ReportPackageManifestSummary {
  return {
    kind: dto?.kind ?? '',
    version: dto?.version ?? null,
    exportedAt: dto?.exportedAt ?? null,
    sourceTaskId: dto?.sourceTask?.id ?? null,
    sourceTaskName: dto?.sourceTask?.name ?? null,
    sourceTaskCaseSetHash: dto?.sourceTask?.caseSetHash ?? null,
    entities: dto?.entities ?? [],
    docVersionScope: dto?.docVersionScope ?? null,
    stats: dto?.stats ?? {},
  }
}
