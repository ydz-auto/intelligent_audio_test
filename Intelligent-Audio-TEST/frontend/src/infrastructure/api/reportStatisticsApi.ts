// -*- coding: utf-8 -*-
/**
 * 报告统计分析 API（G04，INT-859 接线）
 *
 * 后端契约：api_gateway/routes/report_bp.py `/reports/statistics*` 三端点
 * （INT-791 落地，doc/接口文档/06_报告管理.md §8）。权限：report:read。
 * - GET  /reports/statistics        统计维度/统计结果（dimension=time|task_type|device_type|evaluation_metric、start_time、end_time、algorithm_type）
 * - GET  /reports/statistics/trend  趋势分析（trend_type=time|dimension、metric、start_time、end_time）
 * - POST /reports/statistics/report 报表生成（report_type、format csv|excel|pdf|html、content、time_range）→ Blob 下载
 * 请求/响应键名转换全部收敛在 reportStatisticsAdapter。
 */
import { request, type RequestOptions } from '../http/client'
import {
  toReportStatistics,
  toReportStatisticsTrend,
  toReportStatisticsQueryDto,
  toReportStatisticsTrendQueryDto,
  toGenerateStatisticsReportDto,
} from '../adapters/reportStatisticsAdapter'
import type {
  ReportStatisticsData,
  ReportStatisticsQuery,
  ReportStatisticsTrendData,
  ReportStatisticsTrendQuery,
  GenerateReportParams,
} from '../../domain/model/reportStatistics'
import type {
  ReportStatisticsDataDto,
  ReportStatisticsTrendDataDto,
} from '../dto/reportStatisticsDto'

export const reportStatisticsApi = {
  /**
   * 统计分析（统计维度/统计结果）
   * GET /reports/statistics → { dimension, overview, detail, chart, anomaly }
   */
  async getStatistics(params: ReportStatisticsQuery = {}, options: RequestOptions = {}): Promise<ReportStatisticsData> {
    const dto = await request<ReportStatisticsDataDto>('GET', '/reports/statistics', null, {
      ...options,
      params: toReportStatisticsQueryDto(params),
    })
    return toReportStatistics(dto)
  },

  /**
   * 趋势分析
   * GET /reports/statistics/trend → { trend_type, metric?, time_trend, dimension_trend }
   */
  async getTrend(params: ReportStatisticsTrendQuery, options: RequestOptions = {}): Promise<ReportStatisticsTrendData> {
    const dto = await request<ReportStatisticsTrendDataDto>('GET', '/reports/statistics/trend', null, {
      ...options,
      params: toReportStatisticsTrendQueryDto(params),
    })
    return toReportStatisticsTrend(dto)
  },

  /**
   * 报表生成（POST /reports/statistics/report）→ Blob 文件下载
   * BFF 复用 binary 下载链路：后端 JSON content_base64 由路由层转 Content-Disposition 附件；
   * 请求失败（400）返回 JSON 错误体（blob），此处识别并抛出业务错误。
   */
  async generateReport(params: GenerateReportParams, options: RequestOptions = {}): Promise<Blob> {
    const blob = await request<Blob>('POST', '/reports/statistics/report', toGenerateStatisticsReportDto(params), {
      ...options,
      responseType: 'blob',
    })
    if (blob && blob.type && blob.type.includes('application/json')) {
      const text = await blob.text()
      try {
        const data = JSON.parse(text)
        throw new Error(data?.message || data?.detail || '报表生成失败')
      } catch (e) {
        if (e instanceof SyntaxError) return blob
        throw e
      }
    }
    return blob
  },
}
