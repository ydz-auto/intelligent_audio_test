/**
 * 任务数据导入导出 API（infrastructure/api 层；接线 INT-694 / 增量回导 INT-1765）。
 * 对照 api_gateway/routes/data_transfer_bp.py（前缀 /api/v1/data-transfer）：
 *   POST /export                导出任务数据为 ZIP（task:export；FileResponse 二进制流直出）
 *   POST /export-incremental    增量导出：新评估 + 新报告子集（task:export，链路 2 / INT-1761）
 *   POST /import/preview        导入预检（task:import，multipart）
 *   POST /import                执行导入（task:import，multipart，长耗时；实时进度走
 *                               SocketIO import_progress，本层以 GET /import/progress 兜底轮询）
 *   POST /import-incremental    增量导入：合并回原任务（task:import，multipart，链路 2 / INT-1761）
 *   GET  /import/progress       最近一次导入进度快照
 * 请求一律经 infrastructure/api/client.ts（ApiError 中文文案透出），页面层只见 camelCase Domain。
 */
import type {
  DataTransferOptions,
  ImportPreview,
  ImportProgress,
  ImportResult,
  IncrementalExportOptions,
  IncrementalImportPreview,
  IncrementalImportResult,
} from '@/domain/models/data-transfer'
import { apiClient } from '@/infrastructure/api/client'
import {
  toImportPreview,
  toImportProgress,
  toImportResult,
  toIncrementalImportPreview,
  toIncrementalImportResult,
  type ImportProgressDto,
  type TaskDataExportDto,
  type TaskDataIncrementalExportDto,
  type TaskImportPreviewDto,
  type TaskImportResultDto,
  type TaskIncrementalImportResultDto,
} from '@/infrastructure/dto/data-transfer.dto'

/** 导出任务数据 ZIP（响应为二进制流；task_export_<timestamp>.zip） */
export async function exportTasks(
  taskIds: number[],
  options: DataTransferOptions
): Promise<Blob> {
  const body: TaskDataExportDto = {
    task_ids: taskIds,
    include_ref_params: options.includeRefParams,
    include_audios: options.includeAudios,
  }
  return apiClient.post<Blob>('/data-transfer/export', body, {
    responseType: 'blob',
    unwrapResponse: false,
  })
}

/** 导入预检（multipart：选文件 → 预检结果） */
export async function previewImport(file: File): Promise<ImportPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const dto = await apiClient.post<TaskImportPreviewDto>(
    '/data-transfer/import/preview',
    formData
  )
  return toImportPreview(dto)
}

/** 执行导入（multipart，长耗时；完成统计 + 失败回滚信息由 ApiError.message/detail 承载） */
export async function executeImport(file: File): Promise<ImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const dto = await apiClient.post<TaskImportResultDto>('/data-transfer/import', formData)
  return toImportResult(dto)
}

/** 最近一次导入进度快照（兜底轮询；无则 null） */
export async function getImportProgress(): Promise<ImportProgress | null> {
  const dto = await apiClient.get<ImportProgressDto | null>('/data-transfer/import/progress')
  return toImportProgress(dto)
}

// ===== 链路 2：增量回导（INT-1765 / 后端 D3 INT-1761） =====

/**
 * 增量导出 ZIP（响应二进制流；incremental_<timestamp>.zip）。
 *
 * 失败语义（后端 HTTP / 顶层 code 同值，明细在响应体 `data`）：
 * - 409 `data.unmappedResultIds`：B 侧存在 A 未登记的结果行（重新执行产生）
 * - 400 `data.taskIds`：增量包只支持单任务
 * - 400 `data.taskId`：B 未整包导入过 A 的数据（source_map 缺失）
 */
export async function exportIncremental(
  taskIds: number[],
  options: IncrementalExportOptions
): Promise<Blob> {
  const body: TaskDataIncrementalExportDto = {
    taskIds,
    include: options.include,
  }
  return apiClient.post<Blob>('/data-transfer/export-incremental', body, {
    responseType: 'blob',
    unwrapResponse: false,
  })
}

/**
 * 增量导入预检（multipart）。
 *
 * 后端 D3 未提供 `/import-incremental/preview`，用整包预检端点解析 1.1 增量包：
 * 返回版本 / 源服务器 / tasks[]（= 源任务）/ stats（含 tableRows 实际行数）/ warnings。
 * 该端点不写任何数据，可安全用于增量包预检。
 */
export async function previewIncrementalImport(file: File): Promise<IncrementalImportPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const dto = await apiClient.post<TaskImportPreviewDto>(
    '/data-transfer/import/preview',
    formData
  )
  return toIncrementalImportPreview(dto)
}

/**
 * 执行增量导入（multipart，长耗时；合并回原任务）。
 *
 * 成功回执：mergedDimensions / deletedDimensions / skippedDimensions / insertedReports /
 * replacedReportId / targetResolvedBy / warnings / batchId / rollbackAvailable。
 * 失败：HTTP 400/403/404/409（前置校验，未写数据，不补偿）或 500（段失败已按逆序补偿，
 * `data.batchId` + `data.compensationErrors`）。
 */
export async function executeIncrementalImport(
  file: File
): Promise<IncrementalImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const dto = await apiClient.post<TaskIncrementalImportResultDto>(
    '/data-transfer/import-incremental',
    formData
  )
  return toIncrementalImportResult(dto)
}
