/**
 * DataTransfer Adapter —— snake_case DTO ↔ camelCase Domain 显式映射
 * 规则同 taskAdapter.ts：逐字段映射，不做 spread 透传。
 */
import type {
  TaskImportPreviewDto,
  TaskImportResultDto,
  ImportProgressDto,
} from '../dto/dataTransferDto'
import type { ImportPreview, ImportResult, ImportProgress, ImportProgressStep } from '../../domain/model/dataTransfer'

const VALID_STEPS: ImportProgressStep[] = [
  'parsing',
  'writing_db',
  'extracting_files',
  'updating_paths',
  'done',
  'error',
]

export function toImportPreview(dto: TaskImportPreviewDto): ImportPreview {
  const stats = dto?.stats ?? {}
  return {
    version: dto?.manifest?.version ?? '',
    exportedAt: dto?.manifest?.exportedAt ?? '',
    source: dto?.manifest?.serverInfo?.source ?? '',
    options: {
      includeRefParams: dto?.manifest?.options?.includeRefParams ?? true,
      includeAudios: dto?.manifest?.options?.includeAudios ?? false,
    },
    tasks: (dto?.manifest?.tasks ?? []).map(t => ({
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
    conflicts: (dto?.conflicts ?? []).map(c => ({
      table: c.table,
      id: c.id,
      existingName: c.existingName ?? '',
    })),
    warnings: dto?.warnings ?? [],
  }
}

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

export function toImportProgress(dto: ImportProgressDto): ImportProgress {
  const step = VALID_STEPS.includes(dto?.step as ImportProgressStep)
    ? (dto.step as ImportProgressStep)
    : 'parsing'
  return {
    step,
    currentTable: dto?.current_table ?? '',
    processedRows: dto?.processed_rows ?? 0,
    totalRows: dto?.total_rows ?? 0,
    percentage: dto?.percentage ?? 0,
    message: dto?.message ?? '',
    batchId: dto?.batch_id ?? '',
  }
}
