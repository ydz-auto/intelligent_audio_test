/**
 * Benchmark 排行区块数据（application 层；15_报告域.md §3.8 + 14_benchmark排行.md §10.3）。
 * 数据经 infrastructure 层获取（GET /benchmarks/reports/{reportId} 后端待立项 →
 * benchmarkApi.ts 留桩 `// 待接线`，FEAT 卡跟踪），adapter 转 Domain 后渲染；
 * 计算中显示骨架/状态，完成后渲染，失败保留上次排行结果 + 错误提示；来源筛选。
 * ECharts 参考线图（中位数/最佳）由组件层独立模块承载，本 hook 只产出排行行数据。
 */
import { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchBenchmarkReportRanking } from '@/infrastructure/api/benchmarkApi'
import { mapBenchmarkReportRanking } from '@/infrastructure/adapters/benchmarkAdapter'
import { publishBenchmarkReport as publishBenchmarkApi } from '@/infrastructure/api/reports-api'
import type {
  BenchmarkReportRankingRow,
  BenchmarkReportSourceFilter,
} from '@/domain/models/benchmark'

export type BenchmarkSourceFilter = BenchmarkReportSourceFilter

export function useBenchmarkRanking(reportId: number) {
  const [source, setSource] = useState<BenchmarkSourceFilter>('all')

  const rankingQuery = useQuery({
    queryKey: ['reports', reportId, 'benchmark-ranking'],
    queryFn: () => fetchBenchmarkReportRanking(reportId).then(mapBenchmarkReportRanking),
    enabled: Boolean(reportId),
  })

  const filteredRows = useCallback(
    (rows: BenchmarkReportRankingRow[]) => {
      switch (source) {
        case 'measured':
          return rows.filter((r) => r.source === 'measured')
        case 'imported':
          return rows.filter((r) => r.source === 'imported')
        case 'diff':
          return rows.filter((r) => r.delta !== null && Math.abs(r.delta as number) > 0)
        default:
          return rows
      }
    },
    [source]
  )

  /** 发布 Benchmark 报告（§3.8；POST /api/v1/benchmarks/reports 生成并发布，已真实接线） */
  const publishBenchmarkReport = useCallback(async () => {
    return publishBenchmarkApi()
  }, [])

  return {
    computing: rankingQuery.isLoading,
    error: rankingQuery.error,
    source,
    setSource,
    data: rankingQuery.data ?? null,
    filteredRows,
    publishBenchmarkReport,
  }
}
