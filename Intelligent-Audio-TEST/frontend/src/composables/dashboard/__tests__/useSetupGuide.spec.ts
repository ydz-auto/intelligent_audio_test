/**
 * INT-736：开始使用引导卡——四步完成度探针 + localStorage 展开/折叠持久化。
 * 探针字段均为 camelCase 域模型（snake_case→camelCase 由 statsAdapter 承担，本层不直读蛇形键）。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useSetupGuide, SETUP_STEPS } from '../useSetupGuide'
import type { HomeStatsDetails } from '../../../domain/model/stats'

function makeDetails(overrides: Partial<HomeStatsDetails> = {}): HomeStatsDetails {
  return {
    testCases: { total: 0, groups: 0 },
    tasks: { total: 0, completed: 0, running: 0, failed: 0 },
    devices: { online: 0, offline: 0, total: 0 },
    audioFiles: { total: 0, dry: 0, noise: 0, prompt: 0, duration: { total: 0, dry: 0, noise: 0, prompt: 0 } },
    playbackDevices: 0,
    apis: { online: 0, offline: 0, total: 0 },
    reports: 0,
    dimensions: { total: 0, withEndpoints: 0, endpoints: 0 },
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('useSetupGuide 完成度探针', () => {
  it('全部为零时四步均未完成，默认展开', () => {
    let d = makeDetails()
    const guide = useSetupGuide(() => d)
    guide.init()
    expect(SETUP_STEPS).toHaveLength(4)
    expect(guide.completedCount.value).toBe(0)
    expect(guide.setupComplete.value).toBe(false)
    expect(guide.expanded.value).toBe(true)
  })

  it('用例/设备/任务/报告 >0 时四步逐项点亮，全部完成默认折叠', () => {
    const d = makeDetails({
      testCases: { total: 3, groups: 1 },
      devices: { online: 2, offline: 0, total: 2 },
      tasks: { total: 5, completed: 2, running: 0, failed: 0 },
      reports: 4,
    })
    const guide = useSetupGuide(() => d)
    guide.init()
    for (const step of SETUP_STEPS) {
      expect(guide.stepCompleted.value(step.key)).toBe(true)
    }
    expect(guide.completedCount.value).toBe(4)
    expect(guide.setupComplete.value).toBe(true)
    // 未手动设置 → 默认折叠
    expect(guide.expanded.value).toBe(false)
  })

  it('设备仅离线不计完成（devices.online>0 判定）', () => {
    const d = makeDetails({
      testCases: { total: 1, groups: 0 },
      devices: { online: 0, offline: 2, total: 2 },
      tasks: { total: 1, completed: 0, running: 0, failed: 0 },
      reports: 1,
    })
    const guide = useSetupGuide(() => d)
    guide.init()
    expect(guide.stepCompleted.value('devices')).toBe(false)
    expect(guide.completedCount.value).toBe(3)
  })

  it('details 为 null（接口未就绪）时探针全 false', () => {
    const guide = useSetupGuide(() => null)
    guide.init()
    expect(guide.completedCount.value).toBe(0)
    expect(guide.expanded.value).toBe(true)
  })
})

describe('useSetupGuide localStorage 持久化', () => {
  it('手动展开/折叠写入 iatp:dashboard:v1:setup-guide', () => {
    const guide = useSetupGuide(() => null)
    guide.init()
    guide.expanded.value = false
    expect(localStorage.getItem('iatp:dashboard:v1:setup-guide')).toBe('collapsed')
    guide.expanded.value = true
    expect(localStorage.getItem('iatp:dashboard:v1:setup-guide')).toBe('expanded')
  })

  it('init 读取持久化态：collapsed 时默认折叠（即使未完成）', () => {
    localStorage.setItem('iatp:dashboard:v1:setup-guide', 'collapsed')
    const guide = useSetupGuide(() => null)
    guide.init()
    expect(guide.expanded.value).toBe(false)
  })

  it('init 读取持久化态：expanded 时默认展开（即使已完成）', () => {
    localStorage.setItem('iatp:dashboard:v1:setup-guide', 'expanded')
    const guide = useSetupGuide(() => null)
    guide.init()
    expect(guide.expanded.value).toBe(true)
  })
})
