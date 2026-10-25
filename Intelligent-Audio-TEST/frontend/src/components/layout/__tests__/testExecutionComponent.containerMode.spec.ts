/**
 * INT-1832 · 规范 18 §2.2/§2.4：容器详情信息头 + 容器版面 —— 组件单测。
 *
 * 锁定口径：
 * - 信息头五类元素：「结果挑选」合并方式徽章、来源 {n} 个任务（Popover）、结果 {m} 条、
 *   用例 {c} 个、创建时间 mono；混合态 `0 < failed < caseCount` → 「部分失败 f/c」，
 *   `failed === caseCount` → 「全部失败」，`failed = 0` 不渲染
 * - 容器版面：信息卡占满整行、进度概览与实时日志不渲染、原页签组不再出现；
 *   「用例清单（c）」「关联资源（d）」两个折叠区默认收起、互不依赖
 * - 非容器：四区（信息 + 进度 + 页签 + 日志）与现状逐项不变
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import TestExecutionComponent from '../TestExecutionComponent.vue'

const authMock = vi.hoisted(() => ({ hasPermission: vi.fn(() => true) }))
vi.mock('../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: authMock.hasPermission }),
}))

const CONTAINER_SOURCE = {
  taskId: 580,
  isCherryPick: true,
  total: 5,
  groups: [
    {
      sourceTaskId: 384,
      sourceTaskName: 'E2E测试任务_2026/9/21 14:09:29',
      results: [{ id: 1, resultId: 3792 }, { id: 2, resultId: 3796 }],
    },
    {
      sourceTaskId: 419,
      sourceTaskName: '小艺拒识E2E测试任务_2026/10/13 17:32:59',
      results: [{ id: 3, resultId: 5714 }, { id: 4, resultId: 5715 }, { id: 5, resultId: 5716 }],
    },
  ],
}

const CASES = [
  { id: 'c1', name: '用例一', executionStatus: 'completed', evaluationStatus: 'completed', duration: 3 },
  { id: 'c2', name: '用例二', executionStatus: 'failed', evaluationStatus: 'completed' },
]
const DEVICES = [{ id: 9, name: 'pura90小艺', status: 'online' }]

const mountExec = (props: Record<string, unknown> = {}) =>
  mount(TestExecutionComponent, {
    props: {
      testType: 'E2E',
      taskInfo: {},
      associatedCases: CASES,
      associatedDevices: DEVICES,
      showLogs: true,
      activeTab: 'cases',
      taskStatus: 'failed',
      ...props,
    },
  })

const mountContainer = (overrides: Record<string, unknown> = {}) =>
  mountExec({
    containerSource: CONTAINER_SOURCE,
    caseCount: 5,
    failedCases: 3,
    createdAt: '2026-10-24T01:07:59Z',
    ...overrides,
  })

describe('TestExecutionComponent 容器信息头（INT-1832 §2.2）', () => {
  it('五类元素取值：合并方式 / 来源 / 结果 / 用例 / 创建时间', () => {
    const w = mountContainer()

    const mergeBadge = w.find('.chb-badge--merge-type')
    expect(mergeBadge.exists()).toBe(true)
    expect(mergeBadge.text()).toBe('结果挑选')

    const text = w.find('.chb-stats').text()
    expect(text).toContain('来源 2 个任务')
    expect(text).toContain('结果 5 条')
    expect(text).toContain('用例 5 个')
    expect(w.find('.chb-created').text()).toMatch(/^创建时间 \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })

  it('混合态：0 < failed < caseCount → 「部分失败 3/5」（warning）', () => {
    const w = mountContainer()
    const warn = w.find('.chb-badge--warning')
    expect(warn.exists()).toBe(true)
    expect(warn.text()).toBe('部分失败 3/5')
  })

  it('混合态：failed === caseCount → 「全部失败」（destructive）', () => {
    const w = mountContainer({ caseCount: 1, failedCases: 1 })
    const badge = w.find('.chb-badge--destructive')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('全部失败')
    expect(w.find('.chb-badge--warning').exists()).toBe(false)
  })

  it('混合态：failed = 0 不渲染任何混态徽章', () => {
    const w = mountContainer({ failedCases: 0 })
    expect(w.find('.chb-badge--warning').exists()).toBe(false)
    expect(w.find('.chb-badge--destructive').exists()).toBe(false)
  })

  it('来源 Popover：点击展开每个来源任务名 + 结果条数；源任务状态位不渲染、不占位', async () => {
    const w = mountContainer()
    expect(w.find('.chb-popover').exists()).toBe(false)

    await w.find('.chb-stat--action').trigger('click')

    const rows = w.findAll('.chb-popover-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].find('.chb-popover-name').text()).toBe('E2E测试任务_2026/9/21 14:09:29')
    expect(rows[0].find('.chb-popover-count').text()).toBe('2 条')
    expect(rows[1].find('.chb-popover-count').text()).toBe('3 条')
    // §11-8 source_task_status 未落地：不占位、不显示「—」
    expect(w.find('.chb-popover').text()).not.toContain('—')
  })

  it('200 且 groups=[] → 信息头照常渲染，来源 0 个任务 + 空 Popover 文案', async () => {
    const w = mountContainer({ containerSource: { ...CONTAINER_SOURCE, groups: [], total: 0 } })
    expect(w.find('.chb-stats').text()).toContain('来源 0 个任务')
    await w.find('.chb-stat--action').trigger('click')
    expect(w.find('.chb-popover-empty').text()).toBe('无来源任务记录')
  })
})

describe('TestExecutionComponent 容器版面（INT-1832 §2.4）', () => {
  it('信息卡占满整行：进度概览不渲染', () => {
    const w = mountContainer()
    expect(w.find('.test-progress-container').classes()).toContain('is-container')
    expect(w.find('.progress-overview').exists()).toBe(false)
  })

  it('实时日志不渲染（容器无执行记录）', () => {
    const w = mountContainer()
    expect(w.find('.real-time-logs').exists()).toBe(false)
  })

  it('原「关联用例 / 关联设备」页签组不再出现，改为两个折叠区且默认收起', async () => {
    const w = mountContainer()
    // v-show 折叠态判定读内联 display（jsdom 的 getComputedStyle 缓存会在展开后滞留旧值，
    // 直接读 style 属性才是 DOM 的真实状态）
    const paneCollapsed = (selector: string) =>
      (w.find(selector).attributes('style') || '').includes('display: none')

    expect(w.find('.association-tabs').exists()).toBe(false)

    const headers = w.findAll('.container-collapse-header')
    expect(headers).toHaveLength(2)
    expect(headers[0].text()).toContain('用例清单（5）')
    expect(headers[1].text()).toContain('关联资源（1）')
    expect(headers[0].attributes('aria-expanded')).toBe('false')
    expect(headers[1].attributes('aria-expanded')).toBe('false')

    // 默认收起
    expect(paneCollapsed('.associated-cases')).toBe(true)
    expect(paneCollapsed('.associated-devices')).toBe(true)

    // 互不依赖：只展开用例清单，关联资源保持收起
    await headers[0].trigger('click')
    expect(headers[0].attributes('aria-expanded')).toBe('true')
    expect(paneCollapsed('.associated-cases')).toBe(false)
    expect(paneCollapsed('.associated-devices')).toBe(true)

    await headers[1].trigger('click')
    expect(paneCollapsed('.associated-devices')).toBe(false)
    // 关联资源列表渲染不变
    expect(w.find('.associated-devices').text()).toContain('pura90小艺')
  })

  it('组成区挂载位存在（P3 填树）：容器形态渲染信息头组件，非容器不渲染', () => {
    const w = mountContainer()
    // 本卡只留 slot 挂载位：无内容时渲染为空，不额外占位报错
    expect(w.findComponent({ name: 'ContainerHeaderBadges' }).exists()).toBe(true)
    expect(mountExec().find('.container-header-badges').exists()).toBe(false)
  })
})

describe('TestExecutionComponent 非容器零变化（INT-1832）', () => {
  it('普通任务：四区（信息 + 进度 + 页签 + 日志）全部保留', () => {
    const w = mountExec()
    const paneCollapsed = (selector: string) =>
      (w.find(selector).attributes('style') || '').includes('display: none')

    expect(w.find('.progress-overview').exists()).toBe(true)
    expect(w.find('.real-time-logs').exists()).toBe(true)
    expect(w.find('.association-tabs').exists()).toBe(true)
    expect(w.find('.container-collapse-header').exists()).toBe(false)
    expect(w.find('.container-header-badges').exists()).toBe(false)

    // 页签语义不变：cases 页签可见，devices 页签隐藏
    expect(paneCollapsed('.associated-cases')).toBe(false)
    expect(paneCollapsed('.associated-devices')).toBe(true)
  })
})
