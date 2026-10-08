/**
 * Data Transfer API module —— 任务数据导入导出（INT-25）
 * 出口契约：Domain（camelCase）；DTO / FormData 组装收敛在本文件。
 */
import { request } from '../http/client';
import { toImportPreview, toImportResult } from '../adapters/dataTransferAdapter';
import type { TaskDataExportDto, TaskImportPreviewDto, TaskImportResultDto } from '../dto/dataTransferDto';
import type { ImportPreview, ImportResult, DataTransferOptions } from '../../domain/model/dataTransfer';

export const dataTransferApi = {
  /** 导出任务数据 ZIP（响应为二进制流） */
  async exportTasks(taskIds: Array<number | string>, options: DataTransferOptions): Promise<Blob> {
    const body: TaskDataExportDto = {
      task_ids: taskIds,
      options: {
        include_ref_params: options.includeRefParams,
        include_audios: options.includeAudios,
      },
    };
    return request<Blob>('POST', '/data-transfer/export', body, { responseType: 'blob' });
  },

  /** 导入预检（multipart） */
  async previewImport(file: File): Promise<ImportPreview> {
    const formData = new FormData();
    formData.append('file', file);
    const dto = await request<TaskImportPreviewDto>('POST', '/data-transfer/import/preview', formData, {
      isMultipart: true,
    });
    return toImportPreview(dto);
  },

  /** 执行导入（multipart，长耗时：进度走 SocketIO import_progress） */
  async executeImport(file: File): Promise<ImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    const dto = await request<TaskImportResultDto>('POST', '/data-transfer/import', formData, {
      isMultipart: true,
    });
    return toImportResult(dto);
  },

  /** 最近一次导入进度快照（兜底） */
  async getImportProgress(): Promise<Record<string, unknown> | null> {
    return request<Record<string, unknown> | null>('GET', '/data-transfer/import/progress', null);
  },
};
