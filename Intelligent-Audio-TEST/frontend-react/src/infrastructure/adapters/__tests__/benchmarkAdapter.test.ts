/**
 * benchmarkAdapter DTO→Domain 单测（14_benchmark排行.md §9 实施清单 #2）：
 * snake_case→camelCase 全字段映射；回归断言：interfaces 层零 snake_case 泄漏。
 */
import { describe, expect, it } from 'vitest'

import {
  filterRankingRows,
  mapMetricMappingDto,
  mapRankingRowDto,
  mapRankingRows,
  mapRankingSubjectDto,
} from '@/infrastructure/adapters/benchmarkAdapter'
import type {
  BenchmarkMetricMappingDto,
  BenchmarkRankingDto,
} from '@/infrastructure/dto/benchmark.dto'
import type { RankingFilters } from '@/domain/models/benchmark'

const ROW_DTO: BenchmarkRankingDto = {
  id: 1001,
  source: 'platform_test',
  category: 'asr',
  metric_code: 'wer',
  metric_name: '字错率',
  unit: '%',
  direction: 'lower_is_better',
  rank: 1,
  total: 10,
  percentile: 5,
  score100: 100,
  subject_name: '远场语音评测模型-旗舰版',
  subject_type: 'closed_source',
  device_type: 'physical',
  benchmark_suite: 'general',
  scenario_key: '通用',
  metric_value: 2.4,
  gap_best: 0,
  gap_median: -2.5,
  delta_external: -0.3,
  published_task_id: 1042,
  published_task_version: 3,
  report_id: 1201,
  baseline_id: null,
  computed_at: '2026-10-16T09:20:00',
}

describe('mapRankingRowDto', () => {
  it('全字段 snake_case → camelCase（interfaces 零 snake_case 断言）', () => {
    const row = mapRankingRowDto(ROW_DTO)

    // 同名直转字段
    expect(row.id).toBe(1001)
    expect(row.source).toBe('platform_test')
    expect(row.category).toBe('asr')
    expect(row.metricCode).toBe('wer')
    expect(row.metricName).toBe('字错率')
    expect(row.unit).toBe('%')
    expect(row.direction).toBe('lower_is_better')
    expect(row.rank).toBe(1)
    expect(row.total).toBe(10)
    expect(row.percentile).toBe(5)
    expect(row.score100).toBe(100)

    // 下划线转驼峰字段
    expect(row.subjectName).toBe('远场语音评测模型-旗舰版')
    expect(row.subjectType).toBe('closed_source')
    expect(row.deviceType).toBe('physical')
    expect(row.benchmarkSuite).toBe('general')
    expect(row.scenarioKey).toBe('通用')
    expect(row.metricValue).toBe(2.4)
    expect(row.gapBest).toBe(0)
    expect(row.gapMedian).toBe(-2.5)
    expect(row.deltaExternal).toBe(-0.3)
    expect(row.publishedTaskId).toBe(1042)
    expect(row.publishedTaskVersion).toBe(3)
    expect(row.reportId).toBe(1201)
    expect(row.baselineId).toBeNull()
    expect(row.computedAt).toBe('2026-10-16T09:20:00')

    // 泄漏断言：Domain 对象不含任何 snake_case 键
    const keys = Object.keys(row) as string[]
    expect(keys.some((key) => key.includes('_'))).toBe(false)
  })

  it('可空字段（device_type/score100/delta_external/baseline_id）原样透传 null', () => {
    const row = mapRankingRowDto({
      ...ROW_DTO,
      device_type: null,
      score100: null,
      delta_external: null,
      baseline_id: 501,
    })
    expect(row.deviceType).toBeNull()
    expect(row.score100).toBeNull()
    expect(row.deltaExternal).toBeNull()
    expect(row.baselineId).toBe(501)
  })
})

describe('mapMetricMappingDto', () => {
  const MAPPING_DTO: BenchmarkMetricMappingDto = {
    id: 1,
    dimension_name: 'WER',
    metric_code: 'wer',
    metric_name: '字错率',
    unit: '%',
    direction: 'lower_is_better',
    scenario_tags: ['普通话通用', '噪声'],
    active: true,
  }

  it('指标映射 DTO → Domain（camelCase）', () => {
    const mapping = mapMetricMappingDto(MAPPING_DTO)
    expect(mapping.dimensionName).toBe('WER')
    expect(mapping.metricCode).toBe('wer')
    expect(mapping.metricName).toBe('字错率')
    expect(mapping.unit).toBe('%')
    expect(mapping.direction).toBe('lower_is_better')
    expect(mapping.scenarioTags).toEqual(['普通话通用', '噪声'])
    expect(mapping.active).toBe(true)
    expect(Object.keys(mapping).some((key) => key.includes('_'))).toBe(false)
  })
})

describe('mapRankingSubjectDto', () => {
  it('主体联想 DTO（string）直透为名称（GET /ranking/subjects 实测返回 string[]）', () => {
    expect(mapRankingSubjectDto('远场语音评测模型-旗舰版')).toBe(
      '远场语音评测模型-旗舰版'
    )
    expect(mapRankingSubjectDto('DeepL API')).toBe('DeepL API')
  })
})

describe('filterRankingRows', () => {
  const rows = [
    mapRankingRowDto(ROW_DTO),
    mapRankingRowDto({
      ...ROW_DTO,
      id: 2001,
      category: 'tts',
      source: 'external_import',
      metric_code: 'mos',
      subject_name: '多音色 TTS 引擎',
      benchmark_suite: 'robustness',
    }),
  ]

  const filters: RankingFilters = {
    category: '',
    suite: '',
    metricCode: '',
    source: '',
    subjectName: '',
  }

  it('全默认筛选返回全部行', () => {
    expect(filterRankingRows(rows, filters)).toHaveLength(2)
  })

  it('按类别 / 测试集 / 指标 / 来源 / 主体筛选逐项生效', () => {
    expect(filterRankingRows(rows, { ...filters, category: 'tts' })).toHaveLength(1)
    expect(filterRankingRows(rows, { ...filters, suite: 'robustness' })).toHaveLength(1)
    expect(filterRankingRows(rows, { ...filters, metricCode: 'wer' })).toHaveLength(1)
    expect(filterRankingRows(rows, { ...filters, source: 'external_import' })).toHaveLength(1)
    expect(
      filterRankingRows(rows, { ...filters, subjectName: '远场' })
    ).toHaveLength(1)
    expect(
      filterRankingRows(rows, { ...filters, subjectName: '不存在的' })
    ).toHaveLength(0)
  })
})

describe('mapRankingRows', () => {
  it('列表整体映射为 camelCase Domain 行', () => {
    const mapped = mapRankingRows([ROW_DTO, { ...ROW_DTO, id: 2001 }])
    expect(mapped).toHaveLength(2)
    expect(mapped[1].id).toBe(2001)
  })
})
