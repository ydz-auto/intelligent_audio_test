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
    options: { includeRefParams?: boolean; includeAudios?: boolean }
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
