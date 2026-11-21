import { describe, expect, it } from 'vitest'

import {
  deviceMonitorStatsFromDto,
  formatStatsDate,
  statsPointFromDto,
} from '@/infrastructure/adapters/deviceMonitorStatsAdapter'
import type {
  DeviceMonitorStatsDto,
  DeviceMonitorStatsPointDto,
} from '@/infrastructure/dto/device-monitor-stats.dto'

const POINT_DTO: DeviceMonitorStatsPointDto = {
  date: '2026-11-21',
  availability: 96.4,
  cpu: 38.2,
  memory: 52,
  battery: 78,
  errors: 1,
  operations: 4,
  health_check_samples: 12,
}

describe('设备监控统计 DTO→Domain（契约 §1.2 / INT-2670 接线）', () => {
  it('日期格式化为 MM-DD，原始 ISO 保留', () => {
    expect(formatStatsDate('2026-11-21')).toBe('11-21')
    expect(statsPointFromDto(POINT_DTO)).toMatchObject({ date: '11-21', isoDate: '2026-11-21' })
  })

  it('非法日期形态原样保留（不静默丢失）', () => {
    expect(formatStatsDate('11-21')).toBe('11-21')
  })

  it('指标 null 原样保留，不补 0（图表断点）', () => {
    const point = statsPointFromDto({
      ...POINT_DTO,
      availability: null,
      cpu: null,
      memory: null,
      battery: null,
    })
    expect(point.availability).toBeNull()
    expect(point.cpu).toBeNull()
    expect(point.memory).toBeNull()
    expect(point.battery).toBeNull()
    // 计数 0 是有效值
    expect(point.errors).toBe(1)
    expect(point.operations).toBe(4)
  })

  it('0 值指标不被当成缺失', () => {
    const point = statsPointFromDto({ ...POINT_DTO, availability: 0, cpu: 0, operations: 0 })
    expect(point.availability).toBe(0)
    expect(point.cpu).toBe(0)
    expect(point.operations).toBe(0)
  })

  it('整体响应映射（含 device_count / 区间）', () => {
    const dto: DeviceMonitorStatsDto = {
      granularity: 'day',
      start_date: '2026-11-15',
      end_date: '2026-11-21',
      device_count: 6,
      points: [POINT_DTO],
    }
    const stats = deviceMonitorStatsFromDto(dto)
    expect(stats.granularity).toBe('day')
    expect(stats.startDate).toBe('2026-11-15')
    expect(stats.endDate).toBe('2026-11-21')
    expect(stats.deviceCount).toBe(6)
    expect(stats.points).toHaveLength(1)
    expect(stats.points[0].healthCheckSamples).toBe(12)
  })

  it('空 points 归一为空数组（空态判定用）', () => {
    expect(
      deviceMonitorStatsFromDto({
        granularity: 'day',
        start_date: '2026-11-21',
        end_date: '2026-11-21',
        device_count: 0,
        points: [],
      }).points
    ).toEqual([])
  })
})
