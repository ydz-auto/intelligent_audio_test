/**
 * APIs (external API services) API module
 * 出口契约：Domain（camelCase）；查询参数/请求体显式 snake_case（page/per_page/…）。
 */
import { request, type RequestOptions } from '../http/client';
import { toAPIConfig, toApiUpsertDto, toApiHealthCheckResult, toApiQueryDto } from '../adapters/apiConfigAdapter';
import { toArrayOrPaginated } from '../adapters/commonAdapter';
import type { APIConfigDto, PaginatedDto, ApiHealthCheckDto, ImportReportDto } from '../dto';
import type { APIConfig, ApiHealthCheckResult } from '../../domain/model/apiConfig';
import type { ExportFile, ImportReport } from '../../domain/model/common';
import {
  buildFallbackExportFilename,
  toExportFile,
  toImportReport,
  toResourceExportQueryDto,
  type ResourceExportParams,
} from '../adapters/fileTransferAdapter';

export const apisApi = {
  /** API 列表 → APIConfig[]；查询参数 camelCase Domain → snake_case query（对齐 ApiListQuery） */
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}): Promise<APIConfig[]> {
    const raw = await request<PaginatedDto<APIConfigDto> | APIConfigDto[]>('GET', '/apis', null, { ...options, params: toApiQueryDto(params) });
    return toArrayOrPaginated(raw, toAPIConfig);
  },

  async getOne(id: string | number): Promise<APIConfig> {
    const dto = await request<APIConfigDto>('GET', `/apis/${id}`);
    return toAPIConfig(dto);
  },

  /** 创建/更新：Domain(camelCase) → snake_case 请求体 */
  async create(apiData: Partial<APIConfig>, options: RequestOptions = {}) {
    return request('POST', '/apis', toApiUpsertDto(apiData), options);
  },

  async update(id: string | number, apiData: Partial<APIConfig>, options: RequestOptions = {}) {
    return request('PUT', `/apis/${id}`, toApiUpsertDto(apiData), options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/apis/${id}`);
  },

  /**
   * 导出 API 配置（INT-816 / INT-1628：GET /apis/export）。
   * format∈{json,excel}（默认 json），ids 为导出白名单；文件名取自 Content-Disposition。
   */
  async exportFile(params: ResourceExportParams = {}, options: RequestOptions = {}): Promise<ExportFile> {
    const blob = await request<Blob>('GET', '/apis/export', null, {
      ...options,
      params: toResourceExportQueryDto(params.ids, params.format) as unknown as Record<string, any>,
      responseType: 'blob',
    });
    const safeBlob = blob instanceof Blob ? blob : new Blob([blob as unknown as BlobPart]);
    return toExportFile(safeBlob, buildFallbackExportFilename('apis', params.format));
  },

  /** 导入 API 配置（POST /apis/import，multipart 字段名 file，按 name 匹配） */
  async importFile(file: File, options: RequestOptions = {}): Promise<ImportReport> {
    const formData = new FormData();
    formData.append('file', file);
    const dto = await request<ImportReportDto>('POST', '/apis/import', formData, {
      ...options,
      isMultipart: true,
    });
    return toImportReport(dto);
  },

  /** 连接测试（POST /apis/{id}/health，后端 health_check 与 test_connection 同实现）→ ApiHealthCheckResult（camelCase） */
  async healthCheck(id: string | number, options: RequestOptions = {}): Promise<ApiHealthCheckResult> {
    const dto = await request<ApiHealthCheckDto>('POST', `/apis/${id}/health`, null, options);
    return toApiHealthCheckResult(dto);
  },

  async testConnection(id: string | number, options: RequestOptions = {}): Promise<ApiHealthCheckResult> {
    return this.healthCheck(id, options);
  },

  async stopTest(id: string | number, options: RequestOptions = {}) {
    return request('POST', `/apis/${id}/stop-test`, null, options);
  }
};
