/**
 * benchmarkReportsApi 契约测试（INT-483）
 * 覆盖：publish 请求体以 snake_case 透传（BenchmarkReportCreateRequest 契约）、
 * 列表/详情 DTO → camelCase Domain 映射（_benchmark_report_dict / 快照 _row_dict）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}))

import { request } from '../../http/client'
import { benchmarkReportsApi } from '../benchmarkReportsApi'

const mockedRequest = vi.mocked(request)

beforeEach(() => {
  mockedRequest.mockReset()
})

describe('benchmarkReportsApi publish 契约', () => {
  it('publish 以 snake_case 透传 task_id/suite/category/source/name/description', async () => {
    mockedRequest.mockResolvedValueOnce({
      id: 5, report_id: 101, task_id: 7, suite: 'librispeech-test-clean', category: 'asr',
      source: 'platform_test', algorithm_set: 'ASR-Baseline', published_task_count: 3,
      subject_count: 12, metric_count: 4, ranking_data: null, version: 1,
      published_by: 'tester', published_at: '2026-10-16T07:00:00', created_at: '2026-10-16T07:00:00', updated_at: '2026-10-16T07:00:00',
    })
    const record = await benchmarkReportsApi.publish({
      taskId: 7, suite: 'librispeech-test-clean', category: 'asr', source: 'platform_test',
      algorithmSet: 'ASR-Baseline', name: 'LibriSpeech 基准报告', description: '正式回归',
    })
    expect(mockedRequest.mock.calls[0][0]).toBe('POST')
    expect(mockedRequest.mock.calls[0][1]).toBe('/benchmarks/reports')
    expect(mockedRequest.mock.calls[0][2]).toEqual({
      task_id: 7,
      suite: 'librispeech-test-clean',
      category: 'asr',
      source: 'platform_test',
      algorithm_set: 'ASR-Baseline',
      name: 'LibriSpeech 基准报告',
      description: '正式回归',
    })
    expect(record.reportId).toBe(101)
    expect(record.publishedTaskCount).toBe(3)
    expect(record.algorithmSet).toBe('ASR-Baseline')
  })

  it('publish 空载荷不发空串字段（全量快照契约）', async () => {
    mockedRequest.mockResolvedValueOnce({ id: 6, report_id: 102, suite: '', category: '', source: '', algorithm_set: '', published_task_count: 0, subject_count: 0, metric_count: 0, version: 1, published_by: '', published_at: null, created_at: null, updated_at: null })
    await benchmarkReportsApi.publish({ name: '全量报告' })
    const body = mockedRequest.mock.calls[0][2] as Record<string, any>
    expect(body).toEqual({ name: '全量报告' })
    expect(body.suite).toBeUndefined()
    expect(body.category).toBeUndefined()
    expect(body.source).toBeUndefined()
  })
})

describe('benchmarkReportsApi list / getOne 契约', () => {
  it('list 以 snake_case 查询参数下发 suite/category/source/per_page，返回 camelCase 信封', async () => {
    mockedRequest.mockResolvedValueOnce({
      items: [
        {
          id: 5, report_id: 101, task_id: null, suite: 'librispeech-test-clean', category: 'asr',
          source: 'platform_test', algorithm_set: '', published_task_count: 3, subject_count: 12,
          metric_count: 4, version: 1, published_by: 'tester',
          published_at: '2026-10-16T07:00:00', created_at: '2026-10-16T07:00:00', updated_at: '2026-10-16T07:00:00',
        },
      ],
      total: 1, page: 1, per_page: 20, pages: 1,
    })
    const page = await benchmarkReportsApi.list({ suite: 'librispeech-test-clean', perPage: 20 })
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/benchmarks/reports', null, {
      params: { suite: 'librispeech-test-clean', per_page: 20 },
    })
    expect(page.items[0].reportId).toBe(101)
    expect(page.items[0].subjectCount).toBe(12)
    expect(page.items[0].rankingData).toBeNull()
    expect(page.total).toBe(1)
    expect(page.perPage).toBe(20)
  })

  it('getOne 返回含排行快照的 camelCase Domain（ranking_data 快照 rows 全字段映射）', async () => {
    mockedRequest.mockResolvedValueOnce({
      id: 5, report_id: 101, task_id: null, suite: 'librispeech-test-clean', category: 'asr',
      source: 'platform_test', algorithm_set: '', published_task_count: 3, subject_count: 12,
      metric_count: 4,
      ranking_data: {
        filters: { suite: 'librispeech-test-clean', category: 'asr', source: 'platform_test' },
        counts: { published_task_count: 3, subject_count: 12, metric_count: 4, row_count: 2 },
        rows: [
          {
            id: 1, source: 'platform_test', published_task_id: 123, published_task_version: 2,
            report_id: 456, baseline_id: null, subject_name: '模型A', subject_type: 'closed_source',
            device_type: 'websocket_api', benchmark_suite: 'librispeech-test-clean', category: 'asr',
            metric_code: 'WER', metric_name: '字错误率', metric_value: 8.5, unit: '%',
            direction: 'lower_is_better', rank: 1, total: 10, percentile: 10.0, score100: 88.0,
            gap_best: 0.0, gap_median: 1.2, delta_external: -0.3, scenario_key: '通用',
            computed_at: '2026-10-16T07:00:00',
          },
        ],
      },
      version: 1, published_by: 'tester',
      published_at: '2026-10-16T07:00:00', created_at: '2026-10-16T07:00:00', updated_at: '2026-10-16T07:00:00',
    })
    const record = await benchmarkReportsApi.getOne(5)
    expect(record.rankingData).not.toBeNull()
    expect(record.rankingData?.filters.category).toBe('asr')
    expect(record.rankingData?.counts.rowCount).toBe(2)
    expect(record.rankingData?.rows[0].metricName).toBe('字错误率')
    expect(record.rankingData?.rows[0].metricValue).toBe(8.5)
    expect(record.rankingData?.rows[0].gapBest).toBe(0.0)
    expect(record.rankingData?.rows[0].scenarioKey).toBe('通用')
  })
})
