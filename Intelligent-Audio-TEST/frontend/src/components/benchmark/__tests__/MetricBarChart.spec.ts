/**
 * INT-482 审计修复：MetricBarChart 横向条形图 tooltip 值回归
 *
 * 图表 indexAxis:'y'（横向条形），chart.js v4 的 parsed = { x: 数据值, y: 类别下标 }：
 * - tooltip 必须取 parsed.x（缺陷 #1，误用 parsed.y 会 hover 显示「1ms」这类类别下标）
 * - 来源取行按 dataIndex 落入绘制序数组，而非按 subjectName 找首行（同主体双轨并存时避免第二柱来源误标）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import MetricBarChart from '../MetricBarChart.vue'
import { BenchmarkSource } from '../../../domain/enums'
import type { BenchmarkRankingGroup, BenchmarkRankingRow } from '../../../domain/model/benchmark'

const chartState = vi.hoisted(() => ({ configs: [] as unknown[] }))

vi.mock('chart.js/auto', () => ({
  // 组件以 new Chart(...) 构造，mock 需为可构造类（vi.fn 不可 new）
  Chart: class {
    destroy = vi.fn()
    constructor(_ctx: unknown, config: unknown) {
      chartState.configs.push(config)
    }
  },
}))

/** chart.js 配置最小切片（仅测试 tooltip callbacks 需要） */
interface TooltipItemLike {
  dataIndex: number
  parsed: { x: number; y: number }
  label: string
}

interface CapturedChartConfig {
  options: {
    plugins: {
      tooltip: {
        callbacks: {
          label: (item: TooltipItemLike) => string
        }
      }
    }
  }
}

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
    direction: 'lower_is_better',
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

function makeGroup(rows: BenchmarkRankingRow[]): BenchmarkRankingGroup {
  return {
    category: 'voice_llm',
    metricCode: 'TTLW',
    metricName: '接管时延',
    scenarioKey: '通用',
    unit: 'ms',
    direction: 'lower_is_better',
    computedAt: '2026-10-16T07:00:00',
    total: rows.length,
    rows,
  }
}

function captureTooltipLabel(group: BenchmarkRankingGroup) {
  mount(MetricBarChart, { props: { group } })
  expect(chartState.configs).toHaveLength(1)
  const config = chartState.configs[0] as CapturedChartConfig
  return config.options.plugins.tooltip.callbacks.label
}

beforeEach(() => {
  chartState.configs.length = 0
  vi.clearAllMocks()
  // jsdom 无 canvas 2D 实现，桩掉让 renderChart 走到 Chart 构造路径以捕获 tooltip 配置
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: vi.fn(() => ({})),
  })
})

describe('MetricBarChart tooltip（审计修复）', () => {
  it('横向条形取值用 parsed.x（数据值），非 parsed.y（类别下标）', () => {
    const label = captureTooltipLabel(makeGroup([
      makeRow({ id: 1, subjectName: 'Moshi', metricValue: 320, rank: 1 }),
      makeRow({ id: 2, subjectName: 'Gemini Live', source: BenchmarkSource.EXTERNAL_IMPORT, metricValue: 290, rank: 2 }),
    ]))
    // 绘制序按名次反转：dataIndex 0 = rank2（Gemini Live）、dataIndex 1 = rank1（Moshi）
    expect(label({ dataIndex: 0, parsed: { x: 290, y: 1 }, label: 'Gemini Live' })).toBe(' 290ms · 外部基线')
    expect(label({ dataIndex: 1, parsed: { x: 320, y: 0 }, label: 'Moshi' })).toBe(' 320ms · 平台实测')
  })

  it('同主体双轨并存时按 dataIndex 取对应来源，不按 subjectName 首行误标', () => {
    const label = captureTooltipLabel(makeGroup([
      makeRow({ id: 1, subjectName: 'Moshi', metricValue: 320, rank: 1 }),
      makeRow({ id: 2, subjectName: 'Moshi', source: BenchmarkSource.EXTERNAL_IMPORT, metricValue: 290, rank: 2 }),
    ]))
    expect(label({ dataIndex: 0, parsed: { x: 290, y: 1 }, label: 'Moshi' })).toBe(' 290ms · 外部基线')
    expect(label({ dataIndex: 1, parsed: { x: 320, y: 0 }, label: 'Moshi' })).toBe(' 320ms · 平台实测')
  })
})
