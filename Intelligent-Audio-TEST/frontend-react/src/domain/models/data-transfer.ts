/**
 * 任务数据导入导出 Domain 模型（domain 层，09_任务域.md §5.12）。
 * 字段形态对照 api_gateway/schemas/data_transfer.py + data_transfer_bp.py 实测契约，
 * 页面层只见 camelCase（snake_case 只在 infrastructure/dto 层出现）。
 */

/** 导出选项（POST /data-transfer/export 请求体语义） */
export interface DataTransferOptions {
  includeRefParams: boolean
  includeAudios: boolean
}

/** 预检任务清单项（ZIP manifest.tasks） */
export interface ImportPreviewTask {
  id: number
  name: string
  type: string
  status: string
  resultCount: number
}

/** ID 冲突项（导入时自动重映射） */
export interface ImportConflict {
  table: string
  id: number | string
  existingName: string
}

/** 导入预检结果（POST /data-transfer/import/preview） */
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

/** 导入完成统计（POST /data-transfer/import；仅冲突时 remappedIds 非空） */
export interface ImportResult {
  importedTasks: number
  importedResults: number
  importedDimensions: number
  importedReports: number
  importedFiles: number
  remappedIds: Record<string, Record<string, number>>
}

export type ImportProgressStep =
  | 'parsing'
  | 'writing_db'
  | 'extracting_files'
  | 'updating_paths'
  | 'done'
  | 'error'

/** 导入进度（GET /data-transfer/import/progress 快照与 socket payload 同构） */
export interface ImportProgress {
  step: ImportProgressStep
  currentTable: string
  processedRows: number
  totalRows: number
  percentage: number
  message: string
  batchId: string
}
