/**
 * Benchmark 排行区块数据（application 层；15_报告域.md §3.8 + 14_benchmark排行.md §10.3）。
 * 异步计算 + 进度轮询（计算中显示进度/状态，完成后渲染；失败保留上次排行结果）+ 来源筛选。
 * 数据 mock（红线④）；接口形态 `GET /api/v1/benchmarks/reports/{reportId}` 排行结果。
 * ECharts 参考线图（中位数/最佳）由组件层独立模块承载，本 hook 只产出排行行数据。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { publishBenchmarkReport as publishBenchmarkApi } from '@/infrastructure/api/reports-api'

export type BenchmarkSourceFilter = 'measured' | 'imported' | 'all' | 'diff'

export interface BenchmarkRankingRow {
  /** 名次 */
  rank: number
  /** 被测主体 */
  subjectName: string
  /** 主体类型（开源模型/闭源模型商业 API/已上线 APP） */
  subjectType: string
  /** 数据来源（实测 / 导入） */
  source: 'measured' | 'imported'
  /** 指标值 */
  metricValue: number
  /** 与头部差距（gap_best） */
  gapBest: number
  /** 百分位（0-100） */
  percentile: number
  /** 实测-导入差异（delta；仅双轨时非空） */
  delta: number | null
}

export interface BenchmarkRankingData {
  /** 版本标注（实测轨 v{publishedTaskVersion}） */
  version: string
  computedAt: string
  rows: BenchmarkRankingRow[]
  /** 中位数参考线 */
  median: number
  /** 最佳参考线（头部指标值） */
  best: number
  metricName: string
  unit: string
}

/** mock 排行结果（多友商横向对比；报告 1185 唤醒性能 Benchmark） */
const MOCK_RANKING: BenchmarkRankingData = {
  version: 'v20261016.1',
  computedAt: '2026-10-16T09:30:00',
  metricName: '唤醒成功率',
  unit: '%',
  median: 93.2,
  best: 97.8,
  rows: [
    { rank: 1, subjectName: '旗舰-01（平台实测）', subjectType: '设备', source: 'measured', metricValue: 97.8, gapBest: 0, percentile: 100, delta: 1.2 },
    { rank: 2, subjectName: 'asr-streaming-v3', subjectType: '商业 API', source: 'measured', metricValue: 96.4, gapBest: -1.4, percentile: 92, delta: null },
    { rank: 3, subjectName: '开源基线 whisper-large', subjectType: '开源模型', source: 'imported', metricValue: 95.1, gapBest: -2.7, percentile: 81, delta: 0.8 },
    { rank: 4, subjectName: '旗舰-02（平台实测）', subjectType: '设备', source: 'measured', metricValue: 94.3, gapBest: -3.5, percentile: 70, delta: -0.4 },
    { rank: 5, subjectName: 'wakeword-detect-v2', subjectType: '商业 API', source: 'measured', metricValue: 93.2, gapBest: -4.6, percentile: 58, delta: null },
    { rank: 6, subjectName: '友商 A 音箱', subjectType: '已上线 APP', source: 'imported', metricValue: 90.6, gapBest: -7.2, percentile: 37, delta: 2.1 },
    { rank: 7, subjectName: '入门-03（平台实测）', subjectType: '设备', source: 'measured', metricValue: 89.4, gapBest: -8.4, percentile: 25, delta: -1.6 },
  ],
}

export function useBenchmarkRanking(reportId: number) {
  const [progress, setProgress] = useState(0)
  const [computing, setComputing] = useState(true)
  const [source, setSource] = useState<BenchmarkSourceFilter>('all')
  const [data, setData] = useState<BenchmarkRankingData | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // 异步计算 + 进度轮询（mock：600ms 推进到 100 → 渲染；失败保留上次结果）
  useEffect(() => {
    setComputing(true)
    setProgress(0)
    let value = 0
    timerRef.current = setInterval(() => {
      value = Math.min(100, value + 12 + Math.round(Math.random() * 8))
      setProgress(value)
      if (value >= 100) {
        if (timerRef.current) clearInterval(timerRef.current)
        setData(MOCK_RANKING)
        setComputing(false)
      }
    }, 90)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    // reportId 变化重新计算（不同报告排行结果不同；mock 同一常量）
  }, [reportId])

  const filteredRows = useCallback(
    (rows: BenchmarkRankingRow[]) => {
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

  /** 发布 Benchmark 报告（§3.8；POST /api/v1/benchmarks/reports 生成并发布；mock 走 API 桩） */
  const publishBenchmarkReport = useCallback(async () => {
    return publishBenchmarkApi()
  }, [])

  return {
    computing,
    progress,
    source,
    setSource,
    data,
    filteredRows,
    publishBenchmarkReport,
  }
}
