/**
 * Benchmark API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 端点前缀 /api/v1/benchmarks（网关 app.py:165 挂载实测）。
 */
import { request, type RequestOptions } from '../http/client'
import {
  toBenchmarkRankingListData,
  toMetricMappingListData,
  toBenchmarkRankingQueryDto,
  toBenchmarkComputeRequestDto,
} from '../adapters/benchmarkAdapter'
import type {
  BenchmarkRankingFilters,
  BenchmarkRankingResult,
  MetricMappingInfo,
} from '../../domain/model/benchmark'
import type {
  BenchmarkRankingListDataDto,
  MetricMappingListDataDto,
} from '../dto/benchmarkDto'

export const benchmarkApi = {
  /**
   * 排行查询：六参数筛选（suite/category/metricCode/source/publishedTaskId/subjectName），
   * 单页全量（INT-297 信封 items/total/page/per_page/pages）。
   */
  async getRanking(filters: BenchmarkRankingFilters = {}, options: RequestOptions = {}): Promise<BenchmarkRankingResult> {
    const dto = await request<BenchmarkRankingListDataDto>('GET', '/benchmarks/ranking', null, {
      ...options,
      params: toBenchmarkRankingQueryDto(filters),
    })
    return toBenchmarkRankingListData(dto)
  },

  /** 参与排行的被测主体去重清单（主体搜索联想数据源） */
  async getRankingSubjects(suite?: string | null): Promise<string[]> {
    const dto = await request<{ items: string[] }>('GET', '/benchmarks/ranking/subjects', null, {
      params: suite ? { suite } : {},
    })
    return dto.items || []
  },

  /** 指标映射清单（指标筛选下拉数据源；activeOnly=true 仅启用项） */
  async getMetricMappings(activeOnly = true, options: RequestOptions = {}): Promise<MetricMappingInfo[]> {
    const dto = await request<MetricMappingListDataDto>('GET', '/benchmarks/metric-mappings', null, {
      ...options,
      params: { activeOnly },
    })
    return toMetricMappingListData(dto)
  },

  /**
   * 全量重算排行（同步接口；失败时后端不触碰 ReadModel，上次排行结果保持可查看）。
   * 返回后由调用方失效缓存并重取。
   */
  async computeRanking(
    suite?: string | null,
    category?: string | null,
    source?: string | null,
    options: RequestOptions = {},
  ): Promise<void> {
    await request('POST', '/benchmarks/ranking/compute', toBenchmarkComputeRequestDto(suite, category, source), options)
  },
}
