/**
 * Benchmark 报告 Adapter 契约测试（INT-483）
 * 覆盖：DTO(snake_case) → Domain(camelCase) 映射（含可空字段回退）、
 * Domain → DTO 请求体/查询参数 snake_case 转换。
 */
import { describe, it, expect } from 'vitest'
import {
  toBenchmarkReportRecord,
  toBenchmarkReportListData,
  toBenchmarkReportSnapshot,
  toBenchmarkSnapshotRow,
  toBenchmarkReportCreateDto,
  toBenchmarkReportListQueryDto,
} from '../benchmarkReportAdapter'
import type {
  BenchmarkReportRecordDto,
  BenchmarkSnapshotRowDto,
} from '../../dto/benchmarkReportDto'

const ROW_DTO: BenchmarkSnapshotRowDto = {
  id: 1,
  source: 'platform_test',
  published_task_id: 123,
  published_task_version: 2,
  report_id: 456,
  baseline_id: null,
  subject_name: '模型A',
  subject_type: 'closed_source',
  device_type: 'websocket_api',
  benchmark_suite: 'librispeech-test-clean',
  category: 'asr',
  metric_code: 'WER',
  metric_name: '字错误率',
  metric_value: 8.5,
  unit: '%',
  direction: 'lower_is_better',
  rank: 1,
  total: 10,
  percentile: 10.0,
  score100: 88.0,
  gap_best: 0.0,
  gap_median: 1.2,
  delta_external: -0.3,
  scenario_key: '通用',
  computed_at: '2026-10-16T07:00:00',
}

describe('toBenchmarkSnapshotRow', () => {
  it('snake_case DTO → camelCase Domain 全字段映射', () => {
    const row = toBenchmarkSnapshotRow(ROW_DTO)
    expect(row.publishedTaskId).toBe(123)
    expect(row.publishedTaskVersion).toBe(2)
    expect(row.reportId).toBe(456)
    expect(row.baselineId).toBeNull()
    expect(row.subjectName).toBe('模型A')
    expect(row.metricName).toBe('字错误率')
    expect(row.metricValue).toBe(8.5)
    expect(row.gapBest).toBe(0.0)
    expect(row.deltaExternal).toBe(-0.3)
    expect(row.scenarioKey).toBe('通用')
  })

  it('可空字段缺省回退 null', () => {
    const row = toBenchmarkSnapshotRow({
      ...ROW_DTO,
      published_task_id: null,
      baseline_id: null,
      percentile: null,
      computed_at: null,
    })
    expect(row.publishedTaskId).toBeNull()
    expect(row.percentile).toBeNull()
    expect(row.computedAt).toBeNull()
  })
})

describe('toBenchmarkReportSnapshot / toBenchmarkReportRecord', () => {
  it('快照 counts 与 filters 映射', () => {
    const snapshot = toBenchmarkReportSnapshot({
      filters: { suite: 'librispeech-test-clean', category: 'asr', source: 'platform_test' },
      counts: { published_task_count: 3, subject_count: 12, metric_count: 4, row_count: 1 },
      rows: [ROW_DTO],
    })
    expect(snapshot.counts.publishedTaskCount).toBe(3)
    expect(snapshot.counts.rowCount).toBe(1)
    expect(snapshot.filters.category).toBe('asr')
    expect(snapshot.rows).toHaveLength(1)
  })

  it('记录字段映射（含 ranking_data 缺省 → null）', () => {
    const dto: BenchmarkReportRecordDto = {
      id: 5, report_id: 101, task_id: null, suite: 's', category: 'asr', source: 'platform_test',
      algorithm_set: '', published_task_count: 3, subject_count: 12, metric_count: 4,
      version: 1, published_by: 'tester', published_at: '2026-10-16T07:00:00',
      created_at: '2026-10-16T07:00:00', updated_at: '2026-10-16T07:00:00',
    }
    const record = toBenchmarkReportRecord(dto)
    expect(record.reportId).toBe(101)
    expect(record.rankingData).toBeNull()
    expect(record.publishedAt).toBe('2026-10-16T07:00:00')
  })

  it('列表信封映射（列表项不携带 ranking_data）', () => {
    const page = toBenchmarkReportListData({
      items: [{ id: 5, report_id: 101, task_id: null, suite: 's', category: 'asr', source: 'platform_test', algorithm_set: '', published_task_count: 1, subject_count: 2, metric_count: 1, version: 1, published_by: '', published_at: null, created_at: null, updated_at: null }],
      total: 1, page: 1, per_page: 20, pages: 1,
    })
    expect(page.items).toHaveLength(1)
    expect(page.total).toBe(1)
    expect(page.perPage).toBe(20)
    expect(page.items[0].rankingData).toBeNull()
  })
})

describe('Domain → DTO 转换', () => {
  it('toBenchmarkReportCreateDto：camelCase → snake_case，空值不发字段', () => {
    expect(toBenchmarkReportCreateDto({
      taskId: 7, suite: 's', category: 'asr', source: 'platform_test',
      algorithmSet: 'A', name: 'n', description: 'd',
    })).toEqual({
      task_id: 7, suite: 's', category: 'asr', source: 'platform_test',
      algorithm_set: 'A', name: 'n', description: 'd',
    })
    expect(toBenchmarkReportCreateDto({ name: 'only' })).toEqual({ name: 'only' })
  })

  it('toBenchmarkReportListQueryDto：camelCase → snake_case 查询参数', () => {
    expect(toBenchmarkReportListQueryDto({ suite: 's', category: 'asr', perPage: 20 })).toEqual({
      suite: 's', category: 'asr', per_page: 20,
    })
    expect(toBenchmarkReportListQueryDto({ page: 2 })).toEqual({ page: 2 })
  })
})
