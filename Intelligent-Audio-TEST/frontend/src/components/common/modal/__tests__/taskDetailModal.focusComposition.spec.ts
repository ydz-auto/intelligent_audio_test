// -*- coding: utf-8 -*-
/**
 * INT-1835 · 规范 18 §3.1：下单成功落点 —— 容器详情组成区滚动定位与 1.2s 高亮（集成单测）。
 *
 * 锁定口径：
 * - 容器 + `focusSection='composition'`：挂载完成后把组成区滚入可视区（block:start），
 *   加 `is-composition-focus` 高亮类，1.2s 后移除
 * - 非容器（source 归一 null）：静默忽略 focus，不滚动、无高亮、不落错态
 * - 未请求落点（常规打开）：不滚动、无高亮
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  getProgress: vi.fn(),
  logsGetAll: vi.fn(),
  getReviewCount: vi.fn(),
  getSource: vi.fn(),
  hasPermission: vi.fn(() => true),
}))

vi.mock('../../../../composables/task/tasksPort', () => ({
  tasksPort: {
    getOne: mocks.getOne,
    getProgress: mocks.getProgress,
    removeCase: vi.fn(),
    stop: vi.fn(),
    control: vi.fn(),
    retry: vi.fn(),
    reevaluate: vi.fn(),
  },
}))

vi.mock('../../../../composables/task/logsPort', () => ({
  logsPort: { getAll: mocks.logsGetAll },
}))

vi.mock('../../../../composables/task/taskChannelPort', () => ({
  taskChannelPort: {
    onTaskProgress: () => () => {},
    onTaskLog: () => () => {},
    subscribeTask: vi.fn(),
    unsubscribeTask: vi.fn(),
    isConnected: () => true,
    onConnectionChange: () => () => {},
  },
}))

vi.mock('../../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: mocks.hasPermission }),
}))

vi.mock('../../../../composables/modal/useModal', () => ({
  useModalControl: () => ({ open: vi.fn() }),
  MODAL_TYPES: { BASIC_CONFIRM: 'BASIC_CONFIRM', TEST_CASE_DETAIL: 'TEST_CASE_DETAIL', REEXECUTE_OPTIONS: 'REEXECUTE_OPTIONS' },
}))

vi.mock('../../../../composables/modal/useNotification', () => ({
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

// INT-1837：容器详情「报告」区走 GET /reports?task_id=（不打真实网络）
vi.mock('../../../../composables/report/reportsPort', () => ({
  reportsPort: { getAll: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, perPage: 1, pages: 1 }) },
}))

vi.mock('@/infrastructure/api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    cherryPickApi: { ...actual.cherryPickApi, getSource: mocks.getSource },
    tasksApi: { ...actual.tasksApi, getReviewCount: mocks.getReviewCount },
  }
})

import TaskDetailModal from '../TaskDetailModal.vue'

const CONTAINER_TASK = {
  id: 580,
  name: '接线测试_容器详情落点',
  description: '挑选合并自 2 个来源任务',
  status: 'failed',
  executionStatus: 'failed',
  caseCount: 5,
  totalCases: 5,
  failedCases: 3,
  createdAt: '2026-10-24T01:07:59Z',
  cases: [
    { id: 'c1', name: '用例一', status: 'completed', executionStatus: 'completed', evaluationStatus: 'completed', duration: 3 },
    { id: 'c2', name: '用例二', status: 'failed', executionStatus: 'failed', evaluationStatus: 'completed' },
  ],
  devices: [{ id: 9, name: 'pura90小艺', status: 'online' }],
  apis: [],
  expectedTotalTime: '',
  usedTime: '',
  expectedCompleteTime: '',
}

const CONTAINER_SOURCE = {
  taskId: 580,
  isCherryPick: true,
  total: 5,
  groups: [
    { sourceTaskId: 384, sourceTaskName: 'E2E测试任务_2026/9/21', results: [{ id: 1, resultId: 3792 }] },
    { sourceTaskId: 419, sourceTaskName: '小艺拒识E2E测试任务_2026/10/13', results: [{ id: 2, resultId: 5714 }] },
  ],
}

let scrollIntoViewSpy: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.clearAllMocks()
  mocks.hasPermission.mockReturnValue(true)
  mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
  mocks.getProgress.mockResolvedValue(null)
  mocks.getReviewCount.mockResolvedValue(0)
  mocks.getOne.mockResolvedValue(CONTAINER_TASK)
  // jsdom 未实现 scrollIntoView
  scrollIntoViewSpy = vi.fn()
  ;(Element.prototype as any).scrollIntoView = scrollIntoViewSpy
})

afterEach(() => {
  vi.restoreAllMocks()
})

const mountModal = async (props: Record<string, unknown> = {}) => {
  const w = mount(TaskDetailModal, { props: { taskId: 580, ...props } })
  await flushPromises()
  await nextTick()
  return w
}

describe('TaskDetailModal 组成区落点（INT-1835）', () => {
  it('容器 + focus=composition → 滚到组成区顶部并高亮，1.2s 后消退', async () => {
    mocks.getSource.mockResolvedValue(CONTAINER_SOURCE)

    const w = await mountModal({ focusSection: 'composition' })

    const composition = w.find('#composition')
    expect(composition.exists()).toBe(true)
    // 定位：组成区滚入可视区（block:start）
    expect(scrollIntoViewSpy).toHaveBeenCalledTimes(1)
    expect(scrollIntoViewSpy.mock.calls[0][0]).toMatchObject({ block: 'start' })
    expect(scrollIntoViewSpy.mock.instances.length).toBeGreaterThan(0)
    // 高亮
    expect(composition.classes()).toContain('is-composition-focus')

    // 1.2s 后高亮类移除
    await new Promise((resolve) => setTimeout(resolve, 1300))
    await nextTick()
    expect(w.find('#composition').classes()).not.toContain('is-composition-focus')

    w.unmount()
  }, 10000)

  it('非容器 + focus=composition → 静默忽略：不滚动、无高亮、不落错态', async () => {
    const apiError: any = new Error('任务不是挑选合并容器')
    apiError.code = 203
    mocks.getSource.mockRejectedValue(apiError)

    const w = await mountModal({ focusSection: 'composition' })

    expect(w.find('#composition').exists()).toBe(false)
    expect(w.find('.is-composition-focus').exists()).toBe(false)
    expect(scrollIntoViewSpy).not.toHaveBeenCalled()
    expect(w.find('.error-state').exists()).toBe(false)
    // 普通任务四区形态不变
    expect(w.find('.progress-overview').exists()).toBe(true)

    w.unmount()
  })

  it('常规打开（无 focusSection）→ 不滚动、无高亮', async () => {
    mocks.getSource.mockResolvedValue(CONTAINER_SOURCE)

    const w = await mountModal()

    expect(w.find('#composition').exists()).toBe(true)
    expect(w.find('.is-composition-focus').exists()).toBe(false)
    expect(scrollIntoViewSpy).not.toHaveBeenCalled()

    w.unmount()
  })
})
