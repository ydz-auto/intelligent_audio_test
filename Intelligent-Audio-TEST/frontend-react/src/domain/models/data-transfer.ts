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

// ===== 增量回导（链路 2，设计文档 §5.1~§5.5 / D3 INT-1761 实际交付） =====

/** 增量包可选段（POST /data-transfer/export-incremental 的 include 取值） */
export type IncrementalInclude = 'dimensions' | 'reports'

/**
 * 增量导出选项。`include` 至少一项：只导评估维度、只导报告、或两者都导。
 * 默认两段全选（设计文档 §5.2 请求示例：["dimensions", "reports"]）。
 */
export interface IncrementalExportOptions {
  include: IncrementalInclude[]
}

/**
 * 增量导入预检结果。
 * 后端 D3 未提供 `/import-incremental/preview`，预检复用整包预检端点
 * （POST /data-transfer/import/preview）解析 1.1 增量包：版本/源服务器/tasks[]/stats/warnings
 * 均由真实接口给出；源任务即 manifest.tasks[0]（增量包单任务）。
 */
export interface IncrementalImportPreview {
  version: string
  exportedAt: string
  source: string
  /** 源任务 A 原始 id（manifest.sourceTask.id === manifest.tasks[0].id） */
  sourceTaskId: number | null
  sourceTaskName: string
  sourceTaskStatus: string
  sourceTaskResultCount: number
  /** 包内维度评分行数（A 侧将被 (result_id, dimension_id) 覆盖集替换） */
  dimensionCount: number
  /** 包内平台报告数（A 侧将原地替换） */
  reportCount: number
  warnings: string[]
}

/** 增量导入结果回执（POST /data-transfer/import-incremental 响应 data，D3 实际字段） */
export interface IncrementalImportResult {
  taskId: number
  /** 合并写入的维度评分行数 */
  mergedDimensions: number
  /** 覆盖集合并时先删除的旧维度行数 */
  deletedDimensions: number
  /** 目标库匹配不到维度定义而跳过的维度 id 清单 */
  skippedDimensions: number[]
  /** 原地替换 / 新建的报告数 */
  insertedReports: number
  /** 被替换的 A 报告 id（新建时为 null） */
  replacedReportId: number | null
  /** 目标报告定位依据（source_map / latest_task_report / created） */
  targetResolvedBy: string
  warnings: string[]
  batchId: string
  /** 批次快照是否可回滚（7 天保留） */
  rollbackAvailable: boolean
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
  // 增量回导两段跨服务合并（INT-1761：evaluation → report）
  | 'merging_dimensions'
  | 'replacing_reports'
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
