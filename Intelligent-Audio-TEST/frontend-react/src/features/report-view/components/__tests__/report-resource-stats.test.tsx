/**
 * 报告详情「设备与 API 统计」设备副标题（INT-2640）：
 * device_stats.type 走三值白名单再取中文文案——三值显示真机 / HTTP API / Realtime WS，
 * 存量 phone 等脏值统一「未知」，不得外露后端原始英文枚举。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ReportDeviceStat, ReportDetailData } from '@/domain/models/report'
import { ReportResourceStats } from '@/features/report-view/components/report-resource-stats'

function deviceStat(overrides: Partial<ReportDeviceStat> = {}): ReportDeviceStat {
  return {
    id: 10,
    name: 'pura90豆包',
    model: 'Harmony Device',
    type: 'phone',
    status: 'online',
    total_cases: 12,
    completed_cases: 12,
    failed_cases: 1,
    success_rate: 91.7,
    ...overrides,
  }
}

function reportWith(deviceStats: ReportDeviceStat[]): ReportDetailData {
  return {
    id: 426,
    name: '全类型覆盖报告_task460_20261031-100112',
    type: 'task',
    task_name: '全类型覆盖',
    status: 'published',
    created_at: '2026-10-31T10:01:12',
    summary: {
      total_cases: 12,
      completed_cases: 12,
      failed_cases: 1,
      resources: [],
      resource_headers: [],
      raw_data: [],
      metric_data: [],
      tag_metric_data: [],
      case_categories: [],
      all_case_tags: [],
      all_metrics: [],
      case_type_stats: [],
      device_stats: deviceStats,
      api_stats: [],
      devices: [],
      apis: [],
    },
  }
}

describe('ReportResourceStats 设备类型展示（INT-2640）', () => {
  it('历史 phone 副标题归一为「未知」，不外露英文原值', () => {
    render(<ReportResourceStats report={reportWith([deviceStat()])} />)

    expect(screen.getByText('Harmony Device · 未知')).toBeInTheDocument()
    expect(screen.queryByText(/phone/)).not.toBeInTheDocument()
  })

  it('三值类型显示对应中文文案', () => {
    render(
      <ReportResourceStats
        report={reportWith([
          deviceStat({ id: 1, name: '真机设备', type: 'physical' }),
          deviceStat({ id: 2, name: 'HTTP 设备', type: 'http_api' }),
          deviceStat({ id: 3, name: 'WS 设备', type: 'websocket_api' }),
        ])}
      />
    )

    expect(screen.getByText('Harmony Device · 真机')).toBeInTheDocument()
    expect(screen.getByText('Harmony Device · HTTP API')).toBeInTheDocument()
    expect(screen.getByText('Harmony Device · Realtime WS')).toBeInTheDocument()
  })
})
