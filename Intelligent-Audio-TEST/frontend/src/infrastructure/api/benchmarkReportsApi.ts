/**
 * Benchmark 报告 API module（INT-483 报告发布接线）
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 端点前缀 /api/v1/benchmarks（网关 app.py:165 挂载实测），
 * 契约对应子卡1（INT-481）BFF 路由：POST/GET /benchmarks/reports(/reports/{id})。
 */
import { request, type RequestOptions } from '../http/client'
import {
  toBenchmarkReportCreateDto,
  toBenchmarkReportListData,
  toBenchmarkReportListQueryDto,
  toBenchmarkReportRecord,
} from '../adapters/benchmarkReportAdapter'
import type {
  BenchmarkReportCreatePayload,
  BenchmarkReportListData,
  BenchmarkReportListQuery,
  BenchmarkReportRecord,
} from '../../domain/model/benchmarkReport'
import type {
  BenchmarkReportListDataDto,
  BenchmarkReportRecordDto,
} from '../dto/benchmarkReportDto'

export const benchmarkReportsApi = {
  /**
   * 发布 Benchmark 报告：聚合当前排行快照 → 复用报告 7 表结构 → benchmark_reports 落库。
   * 全字段可选（空 = 聚合当前全量排行快照）；响应 = 发布记录（含 reportId）。
   */
  async publish(payload: BenchmarkReportCreatePayload = {}, options: RequestOptions = {}): Promise<BenchmarkReportRecord> {
    const dto = await request<BenchmarkReportRecordDto>('POST', '/benchmarks/reports', toBenchmarkReportCreateDto(payload), options)
    return toBenchmarkReportRecord(dto)
  },

  /**
   * Benchmark 报告列表（分页 + suite/category/source 类型筛选）。
   * 列表项不携带大体积排行快照（详情接口再取）。
   */
  async list(query: BenchmarkReportListQuery = {}, options: RequestOptions = {}): Promise<BenchmarkReportListData> {
    const dto = await request<BenchmarkReportListDataDto>('GET', '/benchmarks/reports', null, {
      ...options,
      params: toBenchmarkReportListQueryDto(query),
    })
    return toBenchmarkReportListData(dto)
  },

  /** Benchmark 报告详情（含排行/指标快照数据 rankingData） */
  async getOne(id: string | number, options: RequestOptions = {}): Promise<BenchmarkReportRecord> {
    const dto = await request<BenchmarkReportRecordDto>('GET', `/benchmarks/reports/${id}`, null, options)
    return toBenchmarkReportRecord(dto)
  },
}
