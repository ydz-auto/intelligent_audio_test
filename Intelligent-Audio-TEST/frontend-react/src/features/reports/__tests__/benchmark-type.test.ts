/**
 * INT-500 v2.9 报告类型 benchmark 落位测试（接线卡 INT-643 后不再读 mock 常量）：
 * 常量 chips/徽标含「Benchmark 报告」；fetchReportTypeCounts / fetchBenchmarkReports
 * 经 mock fetch 断言真实端点契约（report_type=benchmark 过滤 + 类型聚合计数）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  REPORT_TYPE_META,
  REPORT_TYPE_OPTIONS,
} from '@/features/reports/constants'
import {
  fetchBenchmarkReports,
  fetchReportTypeCounts,
} from '@/infrastructure/api/reports-api'
import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const LIST_DATA = {
  success: true,
  code: 0,
  data: {
    items: [
      {
        id: 1185,
        name: '唤醒性能 Benchmark 排行报告（2026-10）',
        type: 'benchmark',
        task_name: '多友商横向能力对比',
        algorithm_type: 'wakeword_detect',
        summary: { total_cases: 96, completed_cases: 96, failed_cases: 4, pass_rate: 95.8, task_count: 6 },
        status: 'published',
        is_favorite: true,
        created_at: '2026-10-16T09:30:00',
      },
      {
        id: 1201,
        name: '旗舰音箱全量回归 · 第 3 轮报告',
        type: 'task',
        task_name: '智能音箱旗舰机型全量回归 · 第 3 轮',
        algorithm_type: 'asr_streaming',
        summary: { total_cases: 48, completed_cases: 48, failed_cases: 3, pass_rate: 93.8 },
        status: 'published',
        is_favorite: false,
        created_at: '2026-10-15T09:20:00',
      },
    ],
    total: 2,
    page: 1,
    per_page: 100,
    pages: 1,
  },
}

describe('INT-500 报告类型 benchmark 落位', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

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

  it('fetchReportTypeCounts：GET /reports 全量后按 type 聚合 benchmark 计数', async () => {
    fetchMock.mockResolvedValue(jsonResponse(LIST_DATA))
    const counts = await fetchReportTypeCounts()
    expect(counts.typeCounts.benchmark).toBe(1)
    expect(counts.typeCounts.all).toBe(2)
    expect(counts.typeCounts.task).toBe(1)
    expect(counts.favoriteCount).toBe(1)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain(`${API_BASE_URL}/reports`)
    const query = new URLSearchParams(url.split('?')[1])
    expect(query.get('per_page')).toBe('1000')
    expect(init.method).toBe('GET')
  })

  it('fetchBenchmarkReports：GET /reports 且 report_type=benchmark 过滤', async () => {
    fetchMock.mockResolvedValue(jsonResponse(LIST_DATA))
    const data = await fetchBenchmarkReports()
    // 服务端过滤由后端按 report_type=benchmark 承担；前端只断言请求契约
    expect(Array.isArray(data.items)).toBe(true)

    const [url] = fetchMock.mock.calls[0] as [string]
    const query = new URLSearchParams(url.split('?')[1])
    expect(query.get('report_type')).toBe('benchmark')
    expect(query.get('deleted')).toBe('false')
  })
})
