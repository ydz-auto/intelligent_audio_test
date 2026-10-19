/**
 * 报告统计分析 Adapter 契约测试（INT-859）
 * 覆盖：Domain(camelCase) → DTO(snake_case) 请求体转换（含日期归一化）、
 * DTO(snake_case) → Domain(camelCase) 响应映射。
 */
import { describe, it, expect } from 'vitest'
import {
  toReportStatisticsQueryDto,
  toReportStatisticsTrendQueryDto,
  toGenerateStatisticsReportDto,
  toReportStatistics,
  toReportStatisticsTrend,
} from '../reportStatisticsAdapter'
import type {
  ReportStatisticsDataDto,
  ReportStatisticsTrendDataDto,
} from '../../dto/reportStatisticsDto'

describe('toReportStatisticsQueryDto', () => {
  it('camelCase 查询参数 → snake_case，date-only 归一为 ISO 时刻', () => {
    const dto = toReportStatisticsQueryDto({
      dimension: 'device_type',
      startTime: '2026-10-01',
      endTime: '2026-10-31',
      algorithmType: 'algo-a',
    })
    expect(dto).toEqual({
      dimension: 'device_type',
      start_time: '2026-10-01T00:00:00',
      end_time: '2026-10-31T23:59:59',
      algorithm_type: 'algo-a',
    })
  })

  it('可选字段为空时不携带（后端走默认口径）', () => {
    const dto = toReportStatisticsQueryDto({ dimension: 'time' })
    expect(dto).toEqual({ dimension: 'time' })
  })

  it('已含时分秒的 ISO 字符串原样透传', () => {
    const dto = toReportStatisticsQueryDto({ startTime: '2026-10-01T12:00:00' })
    expect(dto.start_time).toBe('2026-10-01T12:00:00')
  })
})

describe('toReportStatisticsTrendQueryDto', () => {
  it('trend_type/metric/时间范围 → snake_case', () => {
    const dto = toReportStatisticsTrendQueryDto({
      trendType: 'dimension',
      metric: '清晰度',
      startTime: '2026-10-01',
      endTime: '2026-10-31',
    })
    expect(dto).toEqual({
      trend_type: 'dimension',
      metric: '清晰度',
      start_time: '2026-10-01T00:00:00',
      end_time: '2026-10-31T23:59:59',
    })
  })
})

describe('toGenerateStatisticsReportDto', () => {
  it('报表生成参数 → snake_case 请求体（time_range 对象）', () => {
    const dto = toGenerateStatisticsReportDto({
      reportType: 'case_execution',
      format: 'excel',
      content: '本月执行',
      startTime: '2026-10-01',
      endTime: '2026-10-31',
    })
    expect(dto).toEqual({
      report_type: 'case_execution',
      format: 'excel',
      content: '本月执行',
      time_range: {
        start_time: '2026-10-01T00:00:00',
        end_time: '2026-10-31T23:59:59',
      },
    })
  })

  it('content/time_range 为空时不携带', () => {
    const dto = toGenerateStatisticsReportDto({ reportType: 'report_count', format: 'csv' })
    expect(dto).toEqual({ report_type: 'report_count', format: 'csv', time_range: {} })
  })
})

describe('toReportStatistics', () => {
  const DTO: ReportStatisticsDataDto = {
    dimension: 'time',
    overview: {
      report_count: 12,
      completed_reports: 10,
      total_cases: 360,
      completed_cases: 320,
      failed_cases: 40,
      pass_rate: 88.9,
      duration: 7200.0,
    },
    detail: [
      {
        group: '2026-10-01',
        report_count: 3,
        total_cases: 90,
        completed_cases: 80,
        failed_cases: 10,
        pass_rate: 88.9,
        duration: 1800.0,
      },
      {
        metric: '清晰度',
        report_count: 2,
        total_cases: 60,
        completed_cases: 50,
        failed_cases: 10,
        pass_rate: 83.3,
        duration: 900.0,
        average_value: 85.5,
        min: 82.0,
        max: 89.0,
      },
    ],
    chart: {
      categories: ['2026-10-01'],
      series: [
        { name: '报告数量', data: [3] },
        { name: '总用例数', data: [90] },
        { name: '通过率', data: [88.9] },
      ],
    },
    anomaly: [
      {
        type: 'low_pass_rate',
        report_id: 5,
        report_name: 'xxx',
        message: '通过率偏低',
        value: 42.5,
      },
    ],
  }

  it('snake_case DTO → camelCase Domain 全字段映射', () => {
    const domain = toReportStatistics(DTO)
    expect(domain.dimension).toBe('time')
    expect(domain.overview).toEqual({
      reportCount: 12,
      completedReports: 10,
      totalCases: 360,
      completedCases: 320,
      failedCases: 40,
      passRate: 88.9,
      duration: 7200.0,
    })
    expect(domain.detail[0].group).toBe('2026-10-01')
    expect(domain.detail[1].metric).toBe('清晰度')
    expect(domain.detail[1].averageValue).toBe(85.5)
    expect(domain.chart.series[2].name).toBe('通过率')
    expect(domain.anomaly[0]).toEqual({
      type: 'low_pass_rate',
      reportId: 5,
      reportName: 'xxx',
      message: '通过率偏低',
      value: 42.5,
    })
  })
})

describe('toReportStatisticsTrend', () => {
  const DTO: ReportStatisticsTrendDataDto = {
    trend_type: 'time',
    time_trend: [
      { date: '2026-10-01', report_count: 3, total_cases: 90, pass_rate: 88.9, duration: 1800.0 },
    ],
    dimension_trend: [
      { metric: '清晰度', points: [{ date: '2026-10-01', value: 85.5 }] },
    ],
  }

  it('snake_case DTO → camelCase Domain（time_trend/dimension_trend）', () => {
    const domain = toReportStatisticsTrend(DTO)
    expect(domain.trendType).toBe('time')
    expect(domain.timeTrend[0]).toEqual({
      date: '2026-10-01',
      reportCount: 3,
      totalCases: 90,
      passRate: 88.9,
      duration: 1800.0,
    })
    expect(domain.dimensionTrend[0].metric).toBe('清晰度')
    expect(domain.dimensionTrend[0].points[0]).toEqual({ date: '2026-10-01', value: 85.5 })
  })
})
