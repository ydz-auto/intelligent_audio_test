/**
 * INT-410：重执行入口三态准入门控 —— 组件单测。
 *
 * 锁定口径（任务重新执行功能设计文档 §5 约束#1，负责人裁定 2026-10-15）：
 * - completed/failed/stopped：执行详情模态窗「重新执行」按钮可见
 * - pending/queued/running/paused/skipped/merged：按钮不可见（pending 不允许，需先停止）
 * 门控与任务列表/卡片同源 REEXECUTE_ELIGIBLE_STATUSES（domain/enums.ts），禁止散落字面量。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import { TaskStatus, REEXECUTE_ELIGIBLE_STATUSES } from '@/domain/enums'
import TestExecutionComponent from '../TestExecutionComponent.vue'

// INT-401：挑选入口权限门控（task:cherry_pick）——测试环境无 Pinia，mock 授权为全放行
const authMock = vi.hoisted(() => ({ hasPermission: vi.fn(() => true) }))
vi.mock('../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: authMock.hasPermission }),
}))

const RETRY_BTN = '.step-actions button.btn-success'
const PICK_BTN = '.step-actions button.btn-info'

const mountExec = (taskStatus: string) =>
  mount(TestExecutionComponent, {
    props: {
      testType: 'API',
      taskInfo: {},
      associatedCases: [],
      associatedDevices: [],
      showLogs: false,
      activeTab: 'cases',
      taskStatus,
    },
  })

describe('TestExecutionComponent 重执行门控（INT-410 三态准入）', () => {
  it('枚举单一源：REEXECUTE_ELIGIBLE_STATUSES 恰为 completed/failed/stopped 三态', () => {
    expect([...REEXECUTE_ELIGIBLE_STATUSES]).toEqual([
      TaskStatus.COMPLETED,
      TaskStatus.FAILED,
      TaskStatus.STOPPED,
    ])
    expect(REEXECUTE_ELIGIBLE_STATUSES).not.toContain(TaskStatus.PENDING)
  })

  it.each([
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.STOPPED,
  ])('三态 %s：重新执行按钮可见', (status) => {
    const w = mountExec(status)
    const btn = w.find(RETRY_BTN)
    expect(btn.exists(), `三态 ${status} 应展示重执行入口`).toBe(true)
    expect(btn.text()).toContain('重新执行')
  })

  it.each([
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.PAUSED,
    TaskStatus.SKIPPED,
    TaskStatus.MERGED,
  ])('非三态 %s：重新执行按钮不可见（pending 不允许，需先停止）', (status) => {
    const w = mountExec(status)
    expect(w.find(RETRY_BTN).exists(), `非三态 ${status} 不应展示重执行入口`).toBe(false)
  })
})

describe('TestExecutionComponent 挑选入口门控（INT-401 权限可见性）', () => {
  it('终态任务 + task:cherry_pick 授权 → 展示「加入购物车」入口', () => {
    authMock.hasPermission.mockReturnValue(true)
    const w = mountExec(TaskStatus.COMPLETED)
    expect(w.find(PICK_BTN).exists(), '授权下终态任务应展示挑选入口').toBe(true)
    expect(w.find(PICK_BTN).text()).toContain('加入购物车')
  })

  it('终态任务但无 task:cherry_pick 授权 → 隐藏「加入购物车」入口', () => {
    authMock.hasPermission.mockReturnValue(false)
    const w = mountExec(TaskStatus.COMPLETED)
    expect(w.find(PICK_BTN).exists(), '无授权下挑选入口应隐藏').toBe(false)
  })
})
