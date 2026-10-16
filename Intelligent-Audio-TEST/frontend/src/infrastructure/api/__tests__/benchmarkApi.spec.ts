/**
 * Benchmark API 契约测试
 * 覆盖：请求路径/查询参数/请求体的 snake_case 契约、响应 → camelCase Domain 转换。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}))

import { request } from '../../http/client'
import { benchmarkApi } from '../benchmarkApi'

const mockedRequest = vi.mocked(request)

beforeEach(() => {
  mockedRequest.mockReset()
})

describe('getRanking', () => {
  it('GET /benchmarks/ranking 携带 snake_case 查询参数（含双轨 source 筛选）', async () => {
    mockedRequest.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          source: 'platform_test',
          published_task_id: 5,
          published_task_version: 2,
          report_id: 9,
          baseline_id: null,
          subject_name: 'Moshi',
          subject_type: 'open_source',
          device_type: 'websocket_api',
          benchmark_suite: 'full-duplex-v1',
          category: 'voice_llm',
          metric_code: 'TTLW',
          metric_name: '接管时延',
          metric_value: 320.5,
          unit: 'ms',
          direction: 'lower_is_better',
          rank: 2,
          total: 8,
          percentile: 25,
          score100: 72,
          gap_best: 10.5,
          gap_median: 5.2,
          delta_external: null,
          scenario_key: '通用',
          computed_at: '2026-10-16T07:00:00',
        },
      ],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })

    const result = await benchmarkApi.getRanking({
      suite: 'full-duplex-v1',
      category: 'voice_llm',
      metricCode: 'TTLW',
      source: 'platform_test',
      subjectName: 'Moshi',
    })

    expect(mockedRequest).toHaveBeenCalledWith(
      'GET',
      '/benchmarks/ranking',
      null,
      expect.objectContaining({
        params: {
          suite: 'full-duplex-v1',
          category: 'voice_llm',
          metric_code: 'TTLW',
          source: 'platform_test',
          subject_name: 'Moshi',
        },
      }),
    )
    expect(result.items).toHaveLength(1)
    const row = result.items[0]
    expect(row.subjectName).toBe('Moshi')
    expect(row.publishedTaskId).toBe(5)
    expect(row.reportId).toBe(9)
    expect(row.benchmarkSuite).toBe('full-duplex-v1')
    expect(row.metricCode).toBe('TTLW')
    expect(row.metricValue).toBe(320.5)
    expect(row.direction).toBe('lower_is_better')
    expect(row.score100).toBe(72)
    expect(row.computedAt).toBe('2026-10-16T07:00:00')
  })

  it('无筛选时不携带参数（空对象）', async () => {
    mockedRequest.mockResolvedValueOnce({ items: [], total: 0, page: 1, per_page: 1, pages: 0 })
    await benchmarkApi.getRanking({})
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/benchmarks/ranking', null, expect.objectContaining({ params: {} }))
  })
})

describe('getMetricMappings', () => {
  it('GET /benchmarks/metric-mappings 携带 activeOnly 且响应转 camelCase', async () => {
    mockedRequest.mockResolvedValueOnce({
      items: [
        { id: 1, dimension_name: 'WER', metric_code: 'WER', metric_name: '词错误率', unit: '%', direction: 'lower_is_better', scenario_tags: ['通用'], active: true },
      ],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })

    const list = await benchmarkApi.getMetricMappings(true)

    expect(mockedRequest).toHaveBeenCalledWith('GET', '/benchmarks/metric-mappings', null, expect.objectContaining({ params: { activeOnly: true } }))
    expect(list[0].dimensionName).toBe('WER')
    expect(list[0].metricName).toBe('词错误率')
    expect(list[0].direction).toBe('lower_is_better')
  })
})

describe('getRankingSubjects', () => {
  it('GET /benchmarks/ranking/subjects 携带 suite（可选）', async () => {
    mockedRequest.mockResolvedValueOnce({ items: ['Moshi', 'Whisper'], total: 2, page: 1, per_page: 2, pages: 1 })
    const subjects = await benchmarkApi.getRankingSubjects('full-duplex-v1')
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/benchmarks/ranking/subjects', null, expect.objectContaining({ params: { suite: 'full-duplex-v1' } }))
    expect(subjects).toEqual(['Moshi', 'Whisper'])
  })

  it('无 suite 时不携带参数', async () => {
    mockedRequest.mockResolvedValueOnce({ items: [], total: 0, page: 1, per_page: 1, pages: 0 })
    await benchmarkApi.getRankingSubjects(null)
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/benchmarks/ranking/subjects', null, expect.objectContaining({ params: {} }))
  })
})

describe('computeRanking', () => {
  it('POST /benchmarks/ranking/compute 全量重算（空体）', async () => {
    mockedRequest.mockResolvedValueOnce({ code: 0, message: '排行计算完成', data: null })
    await benchmarkApi.computeRanking()
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/benchmarks/ranking/compute', {}, expect.anything())
  })

  it('POST 带筛选维度（suite/category/source）', async () => {
    mockedRequest.mockResolvedValueOnce({ code: 0, message: '排行计算完成', data: null })
    await benchmarkApi.computeRanking('full-duplex-v1', 'voice_llm', 'platform_test')
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/benchmarks/ranking/compute', {
      suite: 'full-duplex-v1',
      category: 'voice_llm',
      source: 'platform_test',
    }, expect.anything())
  })
})
