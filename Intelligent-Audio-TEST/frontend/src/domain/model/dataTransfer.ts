/**
 * Task Data Transfer Domain —— 任务数据导入导出领域契约（camelCase）
 */

export interface DataTransferOptions {
  includeRefParams: boolean
  includeAudios: boolean
}

export interface ImportPreviewTask {
  id: number
  name: string
  type: string
  status: string
  resultCount: number
}

export interface ImportConflict {
  table: string
  id: number | string
  existingName: string
}

export interface ImportPreview {
  version: string
  exportedAt: string
  source: string
  options: DataTransferOptions
  tasks: ImportPreviewTask[]
  stats: {
    taskCount: number
    resultCount: number
    dimensionCount: number
    reportCount: number
    fileCount: number
    totalFileSize: number
  }
  conflicts: ImportConflict[]
  warnings: string[]
}

export interface ImportResult {
  importedTasks: number
  importedResults: number
  importedDimensions: number
  importedReports: number
  importedFiles: number
  /** 仅冲突时非空：{tasks: {'12': 25}, ...} */
  remappedIds: Record<string, Record<string, number>>
}

export type ImportProgressStep =
  | 'parsing'
  | 'writing_db'
  | 'extracting_files'
  | 'updating_paths'
  | 'done'
  | 'error'

export interface ImportProgress {
  step: ImportProgressStep
  currentTable: string
  processedRows: number
  totalRows: number
  percentage: number
  message: string
  batchId: string
}
