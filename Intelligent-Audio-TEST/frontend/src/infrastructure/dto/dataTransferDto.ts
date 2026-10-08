/**
 * Task Data Transfer DTO —— 任务数据导入导出（INT-25）
 * snake_case，与 api_gateway /data-transfer 契约一一对应（header 注释同 taskDto.ts）。
 */

/** POST /data-transfer/export 请求体 */
export interface TaskDataExportDto {
  task_ids: Array<number | string>
  options: {
    include_ref_params: boolean
    include_audios: boolean
  }
}

/** manifest 内单任务摘要（ZIP 包文件格式，字段为 camelCase） */
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
  /** 仅冲突时返回：{tasks: {old: new}, test_results: {...}, ...} */
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
