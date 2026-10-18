/**
 * 任务数据导入导出 API（infrastructure/api 层；接线 INT-694）。
 * 对照 api_gateway/routes/data_transfer_bp.py 实测（前缀 /api/v1/data-transfer）：
 *   POST /export            导出任务数据为 ZIP（task:export；FileResponse 二进制流直出）
 *   POST /import/preview    导入预检（task:import，multipart）
 *   POST /import            执行导入（task:import，multipart，长耗时；实时进度走
 *                           SocketIO import_progress，本层以 GET /import/progress 兜底轮询）
 *   GET  /import/progress   最近一次导入进度快照
 * 请求一律经 infrastructure/api/client.ts（ApiError 中文文案透出），页面层只见 camelCase Domain。
 */
import type {
  DataTransferOptions,
  ImportPreview,
  ImportProgress,
  ImportResult,
} from '@/domain/models/data-transfer'
import { apiClient } from '@/infrastructure/api/client'
import {
  toImportPreview,
  toImportProgress,
  toImportResult,
  type ImportProgressDto,
  type TaskDataExportDto,
  type TaskImportPreviewDto,
  type TaskImportResultDto,
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
