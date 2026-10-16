/**
 * INT-482 审计修复：DeltaText 基线差 tooltip 方向语义回归
 *
 * 后端 delta_external = 平台实测值 − 外部基线值；更优/更差随指标 direction 翻转：
 * - higher_is_better：↑=高于基线（更优）、↓=低于基线（更差）
 * - lower_is_better：↑=高于基线（更差）、↓=低于基线（更优）
 * tooltip 与箭头、行色三处语义必须一致（审计缺陷 #2）。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeltaText from '../DeltaText.vue'
import { BenchmarkSource, BenchmarkDirection } from '../../../domain/enums'
import type { BenchmarkRankingRow } from '../../../domain/model/benchmark'

function makeRow(overrides: Partial<BenchmarkRankingRow> = {}): BenchmarkRankingRow {
  return {
    id: 1,
    source: BenchmarkSource.PLATFORM_TEST,
    publishedTaskId: 1,
    publishedTaskVersion: 2,
    reportId: 10,
    baselineId: null,
    subjectName: 'Moshi',
    subjectType: 'open_source',
    deviceType: 'websocket_api',
    benchmarkSuite: 'full-duplex-v1',
    category: 'voice_llm',
    metricCode: 'TTLW',
    metricName: '接管时延',
    metricValue: 320,
    unit: 'ms',
    direction: BenchmarkDirection.LOWER_IS_BETTER,
    rank: 1,
    total: 2,
    percentile: 50,
    score100: 80,
    gapBest: 0,
    gapMedian: 5,
    deltaExternal: -10,
    scenarioKey: '通用',
    computedAt: '2026-10-16T07:00:00',
    ...overrides,
  }
}

function mountDelta(overrides: Partial<BenchmarkRankingRow> = {}) {
  return mount(DeltaText, { props: { row: makeRow(overrides) } })
}

describe('DeltaText 基线差 tooltip 方向语义（审计修复）', () => {
  it('lower_is_better + 平台值高于基线（delta>0）：↑ + 红色更差 + 「高于外部基线（更差）」', () => {
    const wrapper = mountDelta({ deltaExternal: 12 })
    expect(wrapper.find('.delta-arrow').text()).toBe('↑')
    expect(wrapper.classes()).toContain('delta-worse')
    expect(wrapper.attributes('title')).toBe('高于外部基线（更差）')
  })

  it('lower_is_better + 平台值低于基线（delta<0）：↓ + 绿色更优 + 「低于外部基线（更优）」', () => {
    const wrapper = mountDelta({ deltaExternal: -10 })
    expect(wrapper.find('.delta-arrow').text()).toBe('↓')
    expect(wrapper.classes()).toContain('delta-better')
    expect(wrapper.attributes('title')).toBe('低于外部基线（更优）')
  })

  it('higher_is_better + delta>0：↑ + 绿色更优 + 「高于外部基线（更优）」', () => {
    const wrapper = mountDelta({ deltaExternal: 12, direction: BenchmarkDirection.HIGHER_IS_BETTER })
    expect(wrapper.find('.delta-arrow').text()).toBe('↑')
    expect(wrapper.classes()).toContain('delta-better')
    expect(wrapper.attributes('title')).toBe('高于外部基线（更优）')
  })

  it('higher_is_better + delta<0：↓ + 红色更差 + 「低于外部基线（更差）」', () => {
    const wrapper = mountDelta({ deltaExternal: -10, direction: BenchmarkDirection.HIGHER_IS_BETTER })
    expect(wrapper.find('.delta-arrow').text()).toBe('↓')
    expect(wrapper.classes()).toContain('delta-worse')
    expect(wrapper.attributes('title')).toBe('低于外部基线（更差）')
  })

  it('delta 为 0：无箭头无 tooltip，展示占位「—」', () => {
    const wrapper = mountDelta({ deltaExternal: 0 })
    expect(wrapper.find('.delta-arrow').exists()).toBe(false)
    expect(wrapper.attributes('title')).toBe('')
    expect(wrapper.text()).toBe('—')
  })

  it('外部基线轨（source=external_import）：不展示基线差 tooltip', () => {
    const wrapper = mountDelta({ source: BenchmarkSource.EXTERNAL_IMPORT, deltaExternal: null })
    expect(wrapper.find('.delta-arrow').exists()).toBe(false)
    expect(wrapper.attributes('title')).toBe('')
    expect(wrapper.text()).toContain('80 分')
  })
})
