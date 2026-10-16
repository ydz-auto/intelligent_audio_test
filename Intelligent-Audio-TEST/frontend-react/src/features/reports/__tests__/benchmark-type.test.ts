/**
 * INT-500 v2.9 报告类型 benchmark 落位测试：
 * 常量 chips/徽标含「Benchmark 报告」+ 计数含 benchmark + Benchmark 列表接口过滤。
 */
import { describe, expect, it } from 'vitest'

import {
  REPORT_TYPE_META,
  REPORT_TYPE_OPTIONS,
} from '@/features/reports/constants'
import {
  fetchBenchmarkReports,
  fetchReportTypeCounts,
} from '@/infrastructure/api/reports-api'
import { MOCK_REPORT_LIST_ITEMS } from '@/infrastructure/mock/reports-mock'

describe('INT-500 报告类型 benchmark 落位', () => {
  it('类型筛选 chips 含「Benchmark 报告」且默认「全部」', () => {
    expect(REPORT_TYPE_OPTIONS[0].value).toBe('all')
    expect(REPORT_TYPE_OPTIONS[0].label).toBe('全部')
    const benchmark = REPORT_TYPE_OPTIONS.find((o) => o.value === 'benchmark')
    expect(benchmark?.label).toBe('Benchmark 报告')
  })

  it('类型徽标映射含 benchmark', () => {
    expect(REPORT_TYPE_META.benchmark.label).toBe('Benchmark 报告')
    // task/comparison/secondary 既有映射不被破坏
    expect(REPORT_TYPE_META.task.label).toBe('任务报告')
    expect(REPORT_TYPE_META.comparison.label).toBe('对比报告')
    expect(REPORT_TYPE_META.secondary_comparison.label).toBe('二次对比')
  })

  it('mock 列表含 benchmark 项且计数正确', async () => {
    const benchmarkItems = MOCK_REPORT_LIST_ITEMS.filter((i) => i.type === 'benchmark')
    expect(benchmarkItems.length).toBeGreaterThanOrEqual(1)
    const counts = await fetchReportTypeCounts()
    expect(counts.typeCounts.benchmark).toBe(benchmarkItems.length)
    expect(counts.typeCounts.all).toBeGreaterThanOrEqual(counts.typeCounts.benchmark)
  })

  it('Benchmark 列表接口过滤只含 benchmark 类型', async () => {
    const data = await fetchBenchmarkReports()
    expect(data.items.length).toBeGreaterThanOrEqual(1)
    expect(data.items.every((i) => i.type === 'benchmark')).toBe(true)
  })
})
