/**
 * 任务数据导入导出 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway/schemas/data_transfer.py + data_transfer_bp.py 实测契约：
 * POST /data-transfer/export  → TaskDataExportRequest（snake_case 平铺）
 * POST /data-transfer/import/preview → manifest/stats/conflicts/warnings
 * POST /data-transfer/import → imported_* / remapped_ids
 * GET /data-transfer/import/progress → 进度快照（snake_case）
 */
import type {
  DataTransferOptions,
  ImportConflict,
  ImportPreview,
  ImportPreviewTask,
  ImportProgress,
  ImportProgressStep,
  ImportResult,
  IncrementalImportPreview,
  IncrementalImportResult,
} from '@/domain/models/data-transfer'

/** POST /data-transfer/export 请求体（TaskDataExportRequest） */
export interface TaskDataExportDto {
  task_ids: number[]
  include_ref_params: boolean
  include_audios: boolean
}

/** manifest 内单任务摘要（ZIP 包内契约，字段为 camelCase） */
export interface ManifestTaskDto {
  id: number
  name: string
  type: string
  status: string
  resultCount: number
}

/** POST /data-transfer/import/preview 响应 data */
export interface TaskImportPreviewDto {
  manifest: {
    version: string
    exportedAt: string
    serverInfo: { source?: string }
    tasks: ManifestTaskDto[]
    /** 整包：includeRefParams/includeAudios；增量包 1.1：include（dimensions/reports 子集） */
    options: {
      includeRefParams?: boolean
      includeAudios?: boolean
      include?: string[]
    }
  }
  stats: {
    taskCount?: number
    resultCount?: number
    dimensionCount?: number
    reportCount?: number
    fileCount?: number
    totalFileSize?: number
    tableRows?: Record<string, number>
  }
  conflicts: Array<{ table: string; id: number | string; existingName?: string }>
  warnings: string[]
}

/** POST /data-transfer/import 响应 data */
export interface TaskImportResultDto {
  importedTasks: number
  importedResults: number
  importedDimensions: number
  importedReports: number
  importedFiles: number
  remappedIds?: Record<string, Record<string, number>>
}

/**
 * POST /data-transfer/export-incremental 请求体（TaskDataIncrementalExportRequest）。
 * 契约字段为 camelCase（`taskIds` / `include`）；后端 APIModel 的 alias_generator
 * 同时接受 snake_case，本层按契约拼写发送，不做双口径。
 */
export interface TaskDataIncrementalExportDto {
  taskIds: number[]
  include: string[]
}

/**
 * POST /data-transfer/import-incremental 响应 data（D3 实际回执，camelCase）。
 * 对照 task_service/application/task/data_transfer_import_service.py 的 stats 字典。
 */
export interface TaskIncrementalImportResultDto {
  taskId?: number
  mergedDimensions?: number
  deletedDimensions?: number
  skippedDimensions?: number[]
  insertedReports?: number
  replacedReportId?: number | null
  targetResolvedBy?: string
  warnings?: string[]
  batchId?: string
  rollbackAvailable?: boolean
}

/** GET /data-transfer/import/progress 响应 data（快照）与 socket payload 同构 */
export interface ImportProgressDto {
  step: string
  current_table?: string
  processed_rows?: number
  total_rows?: number
  percentage?: number
  message?: string
  batch_id?: string
}

const VALID_STEPS: ImportProgressStep[] = [
  'parsing',
  'writing_db',
  'extracting_files',
  'updating_paths',
  'merging_dimensions',
  'replacing_reports',
  'done',
  'error',
]

/** manifest + stats 明文契约 → Domain ImportPreview（逐字段映射，不做 spread 透传） */
export function toImportPreview(dto: TaskImportPreviewDto): ImportPreview {
  const stats = dto?.stats ?? {}
  return {
    version: dto?.manifest?.version ?? '',
    exportedAt: dto?.manifest?.exportedAt ?? '',
    source: dto?.manifest?.serverInfo?.source ?? '',
    options: {
      includeRefParams: dto?.manifest?.options?.includeRefParams ?? true,
      includeAudios: dto?.manifest?.options?.includeAudios ?? false,
    } as DataTransferOptions,
    tasks: (dto?.manifest?.tasks ?? []).map((t): ImportPreviewTask => ({
      id: t.id,
      name: t.name,
      type: t.type,
      status: t.status,
      resultCount: t.resultCount,
    })),
    stats: {
      taskCount: stats.taskCount ?? 0,
      resultCount: stats.resultCount ?? 0,
      dimensionCount: stats.dimensionCount ?? 0,
      reportCount: stats.reportCount ?? 0,
      fileCount: stats.fileCount ?? 0,
      totalFileSize: stats.totalFileSize ?? 0,
    },
    conflicts: (dto?.conflicts ?? []).map((c): ImportConflict => ({
      table: c.table,
      id: c.id,
      existingName: c.existingName ?? '',
    })),
    warnings: dto?.warnings ?? [],
  }
}

/** POST /data-transfer/import 响应 → Domain ImportResult */
export function toImportResult(dto: TaskImportResultDto): ImportResult {
  return {
    importedTasks: dto?.importedTasks ?? 0,
    importedResults: dto?.importedResults ?? 0,
    importedDimensions: dto?.importedDimensions ?? 0,
    importedReports: dto?.importedReports ?? 0,
    importedFiles: dto?.importedFiles ?? 0,
    remappedIds: dto?.remappedIds ?? {},
  }
}

/**
 * 整包预检响应（1.1 增量包）→ Domain IncrementalImportPreview。
 * 增量包 tasks[] 恒为单条（sourceTask），源任务 id / 名称从它取；
 * 维度/报告数以接口实际返回的 db 行数（stats.tableRows）为准，缺失时回落 manifest stats。
 */
export function toIncrementalImportPreview(
  dto: TaskImportPreviewDto
): IncrementalImportPreview {
  const base = toImportPreview(dto)
  const sourceTask = base.tasks[0]
  const tableRows = dto?.stats?.tableRows ?? {}
  return {
    version: base.version,
    exportedAt: base.exportedAt,
    source: base.source,
    sourceTaskId: sourceTask?.id ?? null,
    sourceTaskName: sourceTask?.name ?? '',
    sourceTaskStatus: sourceTask?.status ?? '',
    sourceTaskResultCount: sourceTask?.resultCount ?? 0,
    dimensionCount: tableRows.test_result_dimensions ?? base.stats.dimensionCount,
    reportCount: tableRows.test_reports ?? base.stats.reportCount,
    warnings: base.warnings,
  }
}

/** POST /data-transfer/import-incremental 响应 data → Domain IncrementalImportResult */
export function toIncrementalImportResult(
  dto: TaskIncrementalImportResultDto
): IncrementalImportResult {
  return {
    taskId: dto?.taskId ?? 0,
    mergedDimensions: dto?.mergedDimensions ?? 0,
    deletedDimensions: dto?.deletedDimensions ?? 0,
    skippedDimensions: dto?.skippedDimensions ?? [],
    insertedReports: dto?.insertedReports ?? 0,
    replacedReportId: dto?.replacedReportId ?? null,
    targetResolvedBy: dto?.targetResolvedBy ?? '',
    warnings: dto?.warnings ?? [],
    batchId: dto?.batchId ?? '',
    rollbackAvailable: dto?.rollbackAvailable ?? false,
  }
}

/** 进度快照 DTO → Domain ImportProgress（非法 step 回落 parsing） */
export function toImportProgress(dto: ImportProgressDto | null): ImportProgress | null {
  if (!dto) return null
  const step = VALID_STEPS.includes(dto.step as ImportProgressStep)
    ? (dto.step as ImportProgressStep)
    : 'parsing'
  return {
    step,
    currentTable: dto.current_table ?? '',
    processedRows: dto.processed_rows ?? 0,
    totalRows: dto.total_rows ?? 0,
    percentage: dto.percentage ?? 0,
    message: dto.message ?? '',
    batchId: dto.batch_id ?? '',
  }
}
