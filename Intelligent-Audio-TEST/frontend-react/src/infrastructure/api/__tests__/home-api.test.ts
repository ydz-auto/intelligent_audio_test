/**
 * home stats API 单测（接线卡 INT-845）：
 * GET /home/stats/details·summary 返回 snake_case DTO，必须经 home-adapter
 * 收敛为 camelCase 域模型（stats.testCases.total 等可读，无 undefined/NaN）。
 * mock 统一 client 的 request 验证转换链。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchHomeStatsDetails } from '@/infrastructure/api/home'
import { fetchHomeStatsSummary } from '@/infrastructure/api/home-api'

const requestMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/client', () => ({
  request: requestMock,
}))

describe('fetchHomeStatsDetails', () => {
  beforeEach(() => {
    requestMock.mockReset()
  })

  it('GET /home/stats/details 返回 camelCase 域模型（testCases.total 可读）', async () => {
    requestMock.mockResolvedValue({
      test_cases: { total: 44, groups: 6 },
      tasks: { total: 46, completed: 30, running: 2, failed: 4 },
      devices: { online: 5, offline: 1, total: 6 },
      audio_files: { total: 1953, dry: 1953, noise: 0, prompt: 0 },
      playback_devices: 12,
      apis: { online: 1, offline: 0, total: 1 },
      reports: 55,
      dimensions: { total: 37, with_endpoints: 0, endpoints: 0 },
      updated_at: '2026-10-18T11:05:08',
    })
    const stats = await fetchHomeStatsDetails()
    // INT-1225：首页门户公开页匿名 401 不跳登录 → details 请求带第 4 参数
    // { skipAuthRedirect: true }（第 3 参数 params 为 undefined）。断言按实现全参数对齐。
    expect(requestMock).toHaveBeenCalledWith('GET', '/home/stats/details', undefined, {
      skipAuthRedirect: true,
    })
    expect(stats.testCases.total).toBe(44)
    expect(stats.testCases.groups).toBe(6)
    expect(stats.tasks).toEqual({ total: 46, completed: 30, running: 2, failed: 4 })
    expect(stats.devices).toEqual({ online: 5, offline: 1, total: 6 })
    expect(stats.audioFiles).toEqual({ total: 1953, dry: 1953, noise: 0, prompt: 0 })
    expect(stats.playbackDevices).toBe(12)
    expect(stats.apis).toEqual({ online: 1, offline: 0, total: 1 })
    expect(stats.reports).toBe(55)
    expect(stats.dimensions).toEqual({ total: 37, withEndpoints: 0, endpoints: 0 })
    expect(stats.updatedAt).toBe('2026-10-18T11:05:08')
  })
})

describe('fetchHomeStatsSummary', () => {
  beforeEach(() => {
    requestMock.mockReset()
  })

  it('GET /home/stats/summary 返回 camelCase 域模型（recentTasks/topGroups/deviceStatus）', async () => {
    requestMock.mockResolvedValue({
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
      top_groups: [{ id: 'g-1', name: '话轮接管', case_count: 211 }],
      device_status: { online: 3, offline: 0 },
    })
    const summary = await fetchHomeStatsSummary()
    expect(requestMock).toHaveBeenCalledWith('GET', '/home/stats/summary')
    expect(summary.recentTasks).toHaveLength(1)
    expect(summary.recentTasks[0]).toMatchObject({
      id: 417,
      name: '豆包拒识环境理解E2E测试任务',
      deviceTypes: [],
      status: 'reevaluate_queued',
      totalCases: 188,
      completedCases: 173,
      createdAt: '2026-09-29T19:43:21',
    })
    expect(summary.topGroups).toEqual([{ id: 'g-1', name: '话轮接管', caseCount: 211 }])
    expect(summary.deviceStatus).toEqual({ online: 3, offline: 0 })
  })
})
