/**
 * 首页/工作台统计适配器测试（INT-728 接线）：
 * snake_case DTO → camelCase 域模型转换 + 空字段收敛（无 undefined/NaN）。
 */
import { describe, expect, it } from 'vitest'

import {
  toHomeStatsDetails,
  toHomeStatsSummary,
} from '@/infrastructure/adapters/dto/home-adapter'
import type {
  HomeStatsDetailsDto,
  HomeStatsSummaryDto,
} from '@/infrastructure/dto/home.dto'

const DETAILS_DTO: HomeStatsDetailsDto = {
  test_cases: { total: 579, groups: 6 },
  tasks: { total: 124, completed: 74, running: 1, failed: 38 },
  devices: { online: 3, offline: 0, total: 3 },
  audio_files: { total: 1953, dry: 1953, noise: 0, prompt: 0 },
  playback_devices: 12,
  apis: { online: 1, offline: 0, total: 1 },
  reports: 55,
  dimensions: { total: 37, with_endpoints: 0, endpoints: 0 },
  updated_at: '2026-10-18T11:05:08',
}

describe('toHomeStatsDetails', () => {
  it('snake_case DTO → camelCase 域模型', () => {
    const domain = toHomeStatsDetails(DETAILS_DTO)
    expect(domain).toEqual({
      testCases: { total: 579, groups: 6 },
      tasks: { total: 124, completed: 74, running: 1, failed: 38 },
      devices: { online: 3, offline: 0, total: 3 },
      audioFiles: { total: 1953, dry: 1953, noise: 0, prompt: 0 },
      playbackDevices: 12,
      apis: { online: 1, offline: 0, total: 1 },
      reports: 55,
      dimensions: { total: 37, withEndpoints: 0, endpoints: 0 },
      updatedAt: '2026-10-18T11:05:08',
    })
  })

  it('缺失/空字段收敛为 0 与 null（无 undefined/NaN）', () => {
    const domain = toHomeStatsDetails(null)
    expect(domain.testCases.total).toBe(0)
    expect(domain.devices.online).toBe(0)
    expect(domain.updatedAt).toBeNull()
    // 抽查无 NaN
    expect(Number.isFinite(domain.tasks.total)).toBe(true)
  })
})

describe('toHomeStatsSummary', () => {
  const SUMMARY_DTO: HomeStatsSummaryDto = {
    recent_tasks: [
      {
        id: 417,
        name: '豆包拒识环境理解E2E测试任务',
        device_types: [],
        status: 'reevaluate_queued',
        total_cases: 188,
        completed_cases: 173,
        created_at: '2026-09-29T19:43:21',
      },
    ],
    top_groups: [
      { id: 'g-1', name: '话轮接管', case_count: 211 },
    ],
    device_status: { online: 3, offline: 0 },
  }

  it('snake_case DTO → camelCase 域模型，algorithm_type 缺省收敛 null', () => {
    const domain = toHomeStatsSummary(SUMMARY_DTO)
    expect(domain.recentTasks).toHaveLength(1)
    expect(domain.recentTasks[0]).toMatchObject({
      id: 417,
      name: '豆包拒识环境理解E2E测试任务',
      deviceTypes: [],
      status: 'reevaluate_queued',
      algorithmType: null,
      totalCases: 188,
      completedCases: 173,
      createdAt: '2026-09-29T19:43:21',
    })
    expect(domain.topGroups[0]).toEqual({ id: 'g-1', name: '话轮接管', caseCount: 211 })
    expect(domain.deviceStatus).toEqual({ online: 3, offline: 0 })
  })

  it('空响应收敛为空数组/0', () => {
    const domain = toHomeStatsSummary(null)
    expect(domain.recentTasks).toEqual([])
    expect(domain.topGroups).toEqual([])
    expect(domain.deviceStatus).toEqual({ online: 0, offline: 0 })
  })
})
