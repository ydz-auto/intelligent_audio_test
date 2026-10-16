/**
 * Benchmark Adapter 契约测试
 * 覆盖：DTO(snake_case) → Domain(camelCase) 映射、查询参数/请求体 snake_case 转换。
 * 字段口径对应 report_service benchmark_repository _row_dict 实测序列化结果。
 */
import { describe, it, expect } from 'vitest'
import {
  toBenchmarkRankingRow,
  toBenchmarkRankingListData,
  toMetricMappingInfo,
  toMetricMappingListData,
  toBenchmarkRankingQueryDto,
  toBenchmarkComputeRequestDto,
} from '../benchmarkAdapter'
import type { BenchmarkRankingRowDto } from '../../dto/benchmarkDto'

const ROW_DTO: BenchmarkRankingRowDto = {
  id: 1,
  source: 'platform_test',
  published_task_id: 123,
  published_task_version: 2,
  report_id: 456,
  baseline_id: null,
  subject_name: 'OpenAI GPT-4o Realtime',
  subject_type: 'closed_source',
  device_type: 'websocket_api',
  benchmark_suite: 'full-duplex-v1',
  category: 'voice_llm',
  metric_code: 'TTLW',
  metric_name: '接管时延',
  metric_value: 123.45,
  unit: 'ms',
  direction: 'lower_is_better',
  rank: 1,
  total: 10,
  percentile: 10.0,
  score100: 85.0,
  gap_best: 0.0,
  gap_median: 12.3,
  delta_external: -5.2,
  scenario_key: '通用',
  computed_at: '2026-10-16T07:00:00',
}

describe('toBenchmarkRankingRow', () => {
  it('snake_case DTO → camelCase Domain 全字段映射', () => {
    const row = toBenchmarkRankingRow(ROW_DTO)
    expect(row.id).toBe(1)
    expect(row.source).toBe('platform_test')
    expect(row.publishedTaskId).toBe(123)
    expect(row.publishedTaskVersion).toBe(2)
    expect(row.reportId).toBe(456)
    expect(row.baselineId).toBeNull()
    expect(row.subjectName).toBe('OpenAI GPT-4o Realtime')
    expect(row.subjectType).toBe('closed_source')
    expect(row.deviceType).toBe('websocket_api')
    expect(row.benchmarkSuite).toBe('full-duplex-v1')
    expect(row.category).toBe('voice_llm')
    expect(row.metricCode).toBe('TTLW')
    expect(row.metricName).toBe('接管时延')
    expect(row.metricValue).toBe(123.45)
    expect(row.unit).toBe('ms')
    expect(row.direction).toBe('lower_is_better')
    expect(row.rank).toBe(1)
    expect(row.total).toBe(10)
    expect(row.percentile).toBe(10.0)
    expect(row.score100).toBe(85.0)
    expect(row.gapBest).toBe(0.0)
    expect(row.gapMedian).toBe(12.3)
    expect(row.deltaExternal).toBe(-5.2)
    expect(row.scenarioKey).toBe('通用')
    expect(row.computedAt).toBe('2026-10-16T07:00:00')
  })

  it('可空字段缺省回退 null（外部轨无溯源、单主体 score100 空）', () => {
    const row = toBenchmarkRankingRow({
      ...ROW_DTO,
      source: 'external_import',
      published_task_id: null,
      report_id: null,
      device_type: null,
      percentile: null,
      score100: null,
      gap_best: null,
      delta_external: null,
      computed_at: null,
    })
    expect(row.source).toBe('external_import')
    expect(row.publishedTaskId).toBeNull()
    expect(row.reportId).toBeNull()
    expect(row.deviceType).toBeNull()
    expect(row.percentile).toBeNull()
    expect(row.score100).toBeNull()
    expect(row.gapBest).toBeNull()
    expect(row.deltaExternal).toBeNull()
    expect(row.computedAt).toBeNull()
  })
})

describe('toBenchmarkRankingListData', () => {
  it('信封 items/total/page/per_page/pages → camelCase', () => {
    const result = toBenchmarkRankingListData({
      items: [ROW_DTO],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })
    expect(result.items).toHaveLength(1)
    expect(result.items[0].subjectName).toBe('OpenAI GPT-4o Realtime')
    expect(result.total).toBe(1)
    expect(result.page).toBe(1)
    expect(result.perPage).toBe(1)
    expect(result.pages).toBe(1)
  })

  it('空信封 items 缺省回退空数组', () => {
    const result = toBenchmarkRankingListData({ items: [], total: 0, page: 1, per_page: 1, pages: 0 })
    expect(result.items).toEqual([])
    expect(result.total).toBe(0)
  })
})

describe('toMetricMappingInfo / toMetricMappingListData', () => {
  it('映射 DTO → Domain（scenario_tags 缺省回退空数组）', () => {
    const info = toMetricMappingInfo({
      id: 1,
      dimension_name: 'WER',
      metric_code: 'WER',
      metric_name: 'Word Error Rate',
      unit: '%',
      direction: 'lower_is_better',
      scenario_tags: ['普通话通用', '噪声'],
      active: true,
    })
    expect(info.id).toBe(1)
    expect(info.dimensionName).toBe('WER')
    expect(info.metricCode).toBe('WER')
    expect(info.metricName).toBe('Word Error Rate')
    expect(info.unit).toBe('%')
    expect(info.direction).toBe('lower_is_better')
    expect(info.scenarioTags).toEqual(['普通话通用', '噪声'])
    expect(info.active).toBe(true)
  })

  it('列表信封 → 清单', () => {
    const list = toMetricMappingListData({
      items: [{ id: 1, dimension_name: 'WER', metric_code: 'WER', metric_name: 'WER', unit: '%', direction: 'lower_is_better', scenario_tags: [], active: true }],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })
    expect(list).toHaveLength(1)
    expect(list[0].dimensionName).toBe('WER')
  })
})

describe('toBenchmarkRankingQueryDto', () => {
  it('camelCase 筛选 → snake_case 查询参数（仅启用维度）', () => {
    const q = toBenchmarkRankingQueryDto({
      suite: 'full-duplex-v1',
      category: 'voice_llm',
      metricCode: 'TTLW',
      source: 'platform_test',
      subjectName: 'GPT-4o',
      publishedTaskId: 7,
    })
    expect(q).toEqual({
      suite: 'full-duplex-v1',
      category: 'voice_llm',
      metric_code: 'TTLW',
      source: 'platform_test',
      subject_name: 'GPT-4o',
      published_task_id: 7,
    })
  })

  it('空/未启用维度不携带（source 只接受 platform_test / external_import）', () => {
    const q = toBenchmarkRankingQueryDto({})
    expect(q).toEqual({})
    const q2 = toBenchmarkRankingQueryDto({ suite: '', source: null, subjectName: undefined })
    expect(q2).toEqual({})
  })
})

describe('toBenchmarkComputeRequestDto', () => {
  it('全可选请求体（缺省=全量重算）', () => {
    expect(toBenchmarkComputeRequestDto()).toEqual({})
    expect(toBenchmarkComputeRequestDto('full-duplex-v1', 'voice_llm', 'platform_test')).toEqual({
      suite: 'full-duplex-v1',
      category: 'voice_llm',
      source: 'platform_test',
    })
    expect(toBenchmarkComputeRequestDto('', 'asr', null)).toEqual({ category: 'asr' })
  })
})
