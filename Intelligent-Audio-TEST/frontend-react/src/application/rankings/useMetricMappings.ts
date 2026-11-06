/**
 * 指标映射查询（application 层，指标筛选下拉数据源）。
 * GET /metric-mappings?activeOnly=true（benchmark:ranking:read）；
 * 失败静默退化——调用方回退为纯文本输入（不打断页面，14_benchmark排行.md §4.3）。
 * INT-730 接线：真实端点，client 解包 data；null/失败抛错由 isFailed 判定。
 */
import { useQuery } from '@tanstack/react-query'

import type { MetricMappingInfo } from '@/domain/models/benchmark'
import { fetchBenchmarkMetricMappings } from '@/infrastructure/api/benchmarkApi'
import { mapMetricMappingDto } from '@/infrastructure/adapters/benchmarkAdapter'

export interface MetricMappingsResult {
  mappings: MetricMappingInfo[]
  isLoading: boolean
  /** 请求失败（接口 403/异常）——指标下拉退化纯文本输入的判定 */
  isFailed: boolean
}

export function useMetricMappings(): MetricMappingsResult {
  const query = useQuery({
    queryKey: ['benchmarks', 'metric-mappings'],
    queryFn: async () => {
      const data = await fetchBenchmarkMetricMappings(true)
      if (!data) {
        throw new Error('查询指标映射失败')
      }
      return data.items.map(mapMetricMappingDto)
    },
    staleTime: 5 * 60_000,
    retry: 1,
  })

  return {
    mappings: query.data ?? [],
    isLoading: query.isLoading && !query.data,
    isFailed: query.isError || (!query.isLoading && !query.data),
  }
}
