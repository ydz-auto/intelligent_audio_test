/**
 * 任务域确认弹窗文案（09_任务域.md §5.3/§5.8/§5.9/§5.10）单元测试。
 * 覆盖行删除/彻底删除/恢复/停止/暂停/继续、批量删除/恢复/彻底删除/发布、
 * 详情停止/暂停·继续、移除用例三阶段文案与 destructive 标志；§5.9 阶段推导。
 */
import { describe, expect, it } from 'vitest'

import {
  buildCaseRemoveDesc,
  buildTaskConfirmCopy,
  getCaseRemovePhase,
  type TaskConfirmState,
} from '@/features/tasks/components/task-confirm-dialogs'

const task = {
  id: 1,
  name: '测试任务',
  description: null,
  status: 'running',
  execution_status: 'running',
  evaluation_status: null,
  device_types: ['e2e'],
  device_count: 1,
  api_count: 0,
  total_cases: 2,
  completed_cases: 0,
  failed_cases: 0,
  is_favorite: false,
  deleted: false,
  created_at: '2026-10-01T00:00:00Z',
  tags: [],
  reports: { count: 0 },
  is_cherry_pick: false,
}

const tasks = [task, { ...task, id: 2, name: '测试任务B' }]

function state(kind: TaskConfirmState['kind'], extra: Partial<TaskConfirmState> = {}): TaskConfirmState {
  if (kind === 'remove-case') return { kind, phase: 'running', ...extra } as TaskConfirmState
  if (kind.startsWith('batch')) return { kind, tasks, ...extra } as TaskConfirmState
  if (kind.startsWith('row')) return { kind, task, ...extra } as TaskConfirmState
  if (kind === 'detail-control') return { kind, action: 'pause', ...extra } as TaskConfirmState
  return { kind, ...extra } as TaskConfirmState
}

describe('buildTaskConfirmCopy', () => {
  it('行删除：§5.10 文案 destructive', () => {
    const copy = buildTaskConfirmCopy(state('row-delete'))
    expect(copy.title).toBe('删除任务')
    expect(copy.desc).toBe('将把 1 个任务移入回收站，可在回收站恢复。')
    expect(copy.confirmText).toBe('删除')
    expect(copy.destructive).toBe(true)
  })

  it('批量删除：§5.10 文案含数量 destructive', () => {
    const copy = buildTaskConfirmCopy(state('batch-delete'))
    expect(copy.title).toBe('批量删除任务')
    expect(copy.desc).toBe('将把 2 个任务移入回收站，可在回收站恢复。')
    expect(copy.confirmText).toBe('删除')
    expect(copy.destructive).toBe(true)
  })

  it('行彻底删除/批量彻底删除：§5.10 文案 destructive', () => {
    const single = buildTaskConfirmCopy(state('row-purge'))
    expect(single.desc).toBe('将永久删除 1 个任务及其全部执行数据，此操作不可恢复。')
    expect(single.confirmText).toBe('彻底删除')
    expect(single.destructive).toBe(true)
    const batch = buildTaskConfirmCopy(state('batch-purge'))
    expect(batch.desc).toBe('将永久删除 2 个任务及其全部执行数据，此操作不可恢复。')
    expect(batch.destructive).toBe(true)
  })

  it('恢复/批量恢复：旧 Vue 基线文案，非 destructive', () => {
    const row = buildTaskConfirmCopy(state('row-restore'))
    expect(row.title).toBe('恢复任务')
    expect(row.desc).toBe('确定要恢复该任务吗？')
    expect(row.confirmText).toBe('恢复')
    expect(row.destructive).toBe(false)
    const batch = buildTaskConfirmCopy(state('batch-restore'))
    expect(batch.desc).toBe('确定要恢复选中的 2 个任务吗？')
    expect(batch.destructive).toBe(false)
  })

  it('停止（行/详情）：§5.8 文案 destructive', () => {
    for (const kind of ['row-stop', 'detail-stop'] as const) {
      const copy = buildTaskConfirmCopy(state(kind))
      expect(copy.title).toBe('停止任务')
      expect(copy.desc).toBe('确定要停止该任务吗？')
      expect(copy.confirmText).toBe('停止')
      expect(copy.destructive).toBe(true)
    }
  })

  it('暂停/继续（行/详情）：旧 Vue 基线文案，非 destructive', () => {
    const pause = buildTaskConfirmCopy(state('row-pause'))
    expect(pause.title).toBe('暂停任务')
    expect(pause.desc).toBe('确定要暂停该测试任务吗？')
    expect(pause.confirmText).toBe('暂停')
    expect(pause.destructive).toBe(false)
    const resume = buildTaskConfirmCopy(state('row-resume'))
    expect(resume.title).toBe('继续任务')
    expect(resume.desc).toBe('确定要继续该测试任务吗？')
    expect(resume.confirmText).toBe('继续')
    expect(resume.destructive).toBe(false)
    const detail = buildTaskConfirmCopy(state('detail-control', { action: 'resume' }))
    expect(detail.confirmText).toBe('继续')
    expect(detail.destructive).toBe(false)
  })

  it('批量发布：§5.3 文案含数量，非 destructive', () => {
    const copy = buildTaskConfirmCopy(state('batch-publish'))
    expect(copy.title).toBe('批量发布')
    expect(copy.desc).toBe(
      '将为选中的 2 个任务发布（名称沿用源任务名，不可发布状态自动跳过）。是否继续？'
    )
    expect(copy.confirmText).toBe('发布')
    expect(copy.destructive).toBe(false)
  })

  it('移除用例：§5.9 三阶段后果文案 destructive', () => {
    const pending = buildTaskConfirmCopy({ kind: 'remove-case', phase: 'pending' })
    expect(pending.desc).toBe('该任务尚未开始执行，用例将被直接移除。')
    const running = buildTaskConfirmCopy({ kind: 'remove-case', phase: 'running' })
    expect(running.desc).toBe(
      '该任务正在执行：若该用例正在执行，其当前轮次将被中断，已产出的执行/评估数据将作废（结果标记排除）。'
    )
    const terminal = buildTaskConfirmCopy({ kind: 'remove-case', phase: 'terminal' })
    expect(terminal.desc).toBe(
      '该任务已结束：用例将从本任务移除，其执行/评估结果将被标记为排除（保审计），报告聚合将重算剔除该用例。'
    )
    expect(pending.confirmText).toBe('移除')
    expect(pending.destructive).toBe(true)
  })
})

describe('getCaseRemovePhase', () => {
  it('待执行/排队 → pending', () => {
    expect(getCaseRemovePhase('pending')).toBe('pending')
    expect(getCaseRemovePhase('queued')).toBe('pending')
  })
  it('执行中/暂停/评估中 → running', () => {
    expect(getCaseRemovePhase('running')).toBe('running')
    expect(getCaseRemovePhase('paused')).toBe('running')
    expect(getCaseRemovePhase('evaluating')).toBe('running')
  })
  it('终态 → terminal', () => {
    for (const s of ['completed', 'failed', 'stopped', 'skipped', 'merged']) {
      expect(getCaseRemovePhase(s)).toBe('terminal')
    }
  })
})

describe('buildCaseRemoveDesc', () => {
  it('三阶段文案逐字（INT-305 口径）', () => {
    expect(buildCaseRemoveDesc('pending')).toBe('该任务尚未开始执行，用例将被直接移除。')
    expect(buildCaseRemoveDesc('running')).toContain('其当前轮次将被中断')
    expect(buildCaseRemoveDesc('terminal')).toContain('报告聚合将重算剔除该用例')
  })
})
