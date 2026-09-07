/**
 * Reports API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 */
import type { PaginatedResult } from '../../domain';
import { request, apiBaseUrl, type RequestOptions } from '../http/client';
import {
  toReport,
  toReportListData,
  toCompareResult,
  toReportUpdateDto,
  toReportSummaryFieldDto,
  toReportListQueryDto,
  toReportBatchDeleteDto,
  toReportExportDto,
  toGenerateTaskReportDto,
  toGetCaseAveragesDto,
  toReportSearchCasesDto,
  toSearchCaseResult,
} from '../adapters/reportAdapter';
import type {
  Report,
  ReportListQuery,
  CompareResult,
} from '../../domain/model/report';
import type {
  ReportListDataDto,
  ReportDto,
  ReportCaseListQueryDto,
  CompareResultDto,
} from '../dto/reportDto';

export const reportsApi = {
  /**
   * 分页报告列表 → PaginatedResult<Report>（camelCase）
   * 查询参数经 toReportListQueryDto 转为后端 ReportListQuery（snake_case）。
   */
  async getAll(params: Partial<ReportListQuery> = {}, options: RequestOptions = {}): Promise<PaginatedResult<Report>> {
    const queryDto = toReportListQueryDto(params);
    const dto = await request<ReportListDataDto>('GET', '/reports', null, { ...options, params: queryDto });
    const list = toReportListData(dto);
    return { items: list.items, total: list.total, page: list.page, perPage: list.perPage, pages: list.pages };
  },

  /** 单个报告 → Report（聚合根形状 + summary） */
  async getOne(id: string | number): Promise<Report> {
    const dto = await request<ReportDto>('GET', `/reports/${id}`);
    return toReport(dto);
  },

  async delete(id: string | number): Promise<void> {
    return request<void>('DELETE', `/reports/${id}`);
  },

  /** 批量删除：后端 batch_delete 直接读 body.ids（非 schema） */
  async batchDelete(ids: (string | number)[], hardDelete = false): Promise<void> {
    return request<void>('POST', '/reports/batch-delete', toReportBatchDeleteDto(ids, hardDelete));
  },

  /** 对比报告：显式 task_ids（CompareReportsRequest）→ CompareResult */
  async compare(taskIds: (string | number)[], name: string | null = null): Promise<CompareResult> {
    const body = {
      task_ids: taskIds,
      ...(name !== null && name !== undefined ? { name } : {}),
    };
    const dto = await request<CompareResultDto>('POST', '/reports/compare', body);
    return toCompareResult(dto);
  },

  /** 二次对比：显式 report_ids（SecondaryCompareRequest）→ CompareResult */
  async secondaryCompare(reportIds: (string | number)[]): Promise<CompareResult> {
    const dto = await request<CompareResultDto>('POST', '/reports/secondary-compare', { report_ids: reportIds });
    return toCompareResult(dto);
  },

  /** 导出（ReportExportRequest: ids + format） */
  async export(reportIds: (string | number)[], format: string = 'excel'): Promise<Blob> {
    return request<Blob>('POST', '/reports/export', toReportExportDto(reportIds, format), { responseType: 'blob' });
  },

  async exportHtml(reportId: string | number): Promise<Blob> {
    return request<Blob>('POST', '/reports/export', toReportExportDto([reportId], 'html'), { responseType: 'blob' });
  },

  getExportHtmlUrl(reportId: string | number): string {
    const base = apiBaseUrl.replace(/\/$/, '');
    return `${base}/reports/export?ids=${reportId}&format=html`;
  },

  /** 生成任务报告（GenerateTaskReportRequest: task_id/name/description） */
  async generateTaskReport(taskId: string | number, name: string | null = null, description: string | null = null) {
    return request('POST', '/reports/generate-task', toGenerateTaskReportDto(taskId, name, description));
  },

  async regenerateReport(reportId: string | number) {
    return request('POST', `/reports/${reportId}/regenerate`);
  },

  /** 用例平均值查询（GetCaseAveragesRequest: task_id/category/tags/categories/include_untagged） */
  async getCaseAveragesByFilters(
    taskId: string | number,
    filters: {
      category?: string | null
      tags?: string[]
      categories?: string[]
      includeUntagged?: boolean | null
    } = {},
    options: RequestOptions = {}
  ) {
    return request('POST', '/reports/case-averages', toGetCaseAveragesDto(taskId, filters), options);
  },

  /**
   * 更新报告：Domain 可编辑字段 → ReportUpdateRequest（name/title/description/analysis/conclusion/status/summary）。
   * 兼容旧调用：
   * - 传 camelCase Domain 片段 → toReportUpdateDto
   * - 传 `{ id, summary }` 部分保存 → summary 字段白名单逆转换
   * - 传其他任意对象 → 原样透传（旧调用方自担契约，W2 清理）
   */
  async update(id: string | number, reportData: Partial<Report> | Record<string, any>) {
    let body: unknown;
    if (reportData instanceof Object && 'createdAt' in reportData) {
      body = toReportUpdateDto(reportData as Partial<Report>);
    } else if (reportData instanceof Object && 'summary' in reportData && Object.keys(reportData).length <= 2) {
      body = toReportSummaryFieldDto((reportData as { summary: Partial<Report['summary']> }).summary ?? {});
    } else {
      body = reportData;
    }
    return request('PUT', `/reports/${id}`, body);
  },

  async publish(id: string | number) {
    return request('POST', ` /reports/${id}/publish`.trim());
  },

  /** 报告用例列表（ReportCaseListQuery: page/per_page/keyword/category/tags） */
  async getCases(id: string | number, params: Partial<Omit<ReportCaseListQueryDto, 'page' | 'per_page'>> & { page?: number; perPage?: number } = {}, options: RequestOptions = {}) {
    const queryDto: ReportCaseListQueryDto = {
      page: params.page ?? 1,
      per_page: params.perPage ?? 20,
      ...(params.keyword !== undefined ? { keyword: params.keyword } : {}),
      ...(params.category !== undefined ? { category: params.category } : {}),
      ...(params.tags !== undefined ? { tags: params.tags } : {}),
    };
    return request('GET', `/reports/${id}/cases`, null, { ...options, params: queryDto });
  },

  /** 报告用例搜索（ReportSearchCasesRequest）—— camelCase 入参转 snake_case 请求体，响应经 adapter 转 camelCase */
  async searchCases(
    id: string | number,
    body: Parameters<typeof toReportSearchCasesDto>[0] | Record<string, any> = {},
    options: RequestOptions = {}
  ): Promise<{ items: Record<string, unknown>[]; total: number }> {
    const b = body as Record<string, any>;
    // 旧调用直接传 snake_case 键，此处双拼写归一
    const normalized = {
      keyword: b.keyword,
      category: b.category,
      categories: b.categories,
      includeUntagged: b.includeUntagged ?? b.include_untagged,
      tags: b.tags,
      metrics: b.metrics,
      sortBy: b.sortBy ?? b.sort_by,
      sortMetric: b.sortMetric ?? b.sort_metric,
      sortOrder: b.sortOrder ?? b.sort_order,
      page: b.page,
      perPage: b.perPage ?? b.per_page,
    };
    const raw = await request('POST', `/reports/${id}/cases/search`, toReportSearchCasesDto(normalized), options);
    return toSearchCaseResult(raw);
  },

  async downloadCaseLogs(reportId: string | number, caseId: string | number): Promise<Blob> {
    return request<Blob>('GET', `/reports/${reportId}/cases/${caseId}/logs/download`, null, { responseType: 'blob' });
  },

  getCaseLogsDownloadUrl(reportId: string | number, caseId: string | number): string {
    const base = apiBaseUrl.replace(/\/$/, '');
    return `${base}/reports/${reportId}/cases/${caseId}/logs/download`;
  }
};
