/**
 * 任务域确认弹窗族（09_任务域.md §5.3/§5.8/§5.9/§5.10，ConfirmDialog + destructive 文案逐字）。
 * INT-949 接线：行删除/彻底删除/恢复/暂停/继续/停止、批量删除/恢复/彻底删除/发布、
 * 详情暂停·继续/停止、移除用例（§5.9 按任务阶段两段文案），点击先弹确认，确认才发请求；
 * 取消不发请求。文案口径：危险确认主钮 destructive；恢复/暂停/继续非 destructive。
 * 移除用例的末例二次确认在 CaseAssociation 内自持（双操作按钮 AlertDialog）。
 */
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { TaskListItem } from '@/domain/models/task'

export type TaskConfirmState =
  | { kind: 'row-delete'; task: TaskListItem }
  | { kind: 'row-purge'; task: TaskListItem }
  | { kind: 'row-restore'; task: TaskListItem }
  | { kind: 'row-stop'; task: TaskListItem }
  | { kind: 'row-pause'; task: TaskListItem }
  | { kind: 'row-resume'; task: TaskListItem }
  | { kind: 'batch-delete'; tasks: TaskListItem[] }
  | { kind: 'batch-restore'; tasks: TaskListItem[] }
  | { kind: 'batch-purge'; tasks: TaskListItem[] }
  | { kind: 'batch-publish'; tasks: TaskListItem[] }
  | { kind: 'detail-stop' }
  | { kind: 'detail-control'; action: 'pause' | 'resume' }
  | { kind: 'remove-case'; phase: CaseRemovePhase }

/** §5.9 移除用例阶段（待执行/排队 · 执行中/评估中/暂停 · 终态） */
export type CaseRemovePhase = 'pending' | 'running' | 'terminal'

/** 终态集合（对齐 task-detail-content isTerminal 口径） */
const TERMINAL_STATUSES = ['completed', 'failed', 'stopped', 'merged', 'skipped']

/** 按任务执行状态推导移除用例阶段（§5.9 两段后果文案分支） */
export function getCaseRemovePhase(status: string | null | undefined): CaseRemovePhase {
  if (status === 'pending' || status === 'queued') return 'pending'
  if (status && TERMINAL_STATUSES.includes(status)) return 'terminal'
  return 'running'
}

/** §5.9 移除用例后果文案（INT-305 口径逐字保留） */
export function buildCaseRemoveDesc(phase: CaseRemovePhase): string {
  switch (phase) {
    case 'pending':
      return '该任务尚未开始执行，用例将被直接移除。'
    case 'running':
      return '该任务正在执行：若该用例正在执行，其当前轮次将被中断，已产出的执行/评估数据将作废（结果标记排除）。'
    case 'terminal':
      return '该任务已结束：用例将从本任务移除，其执行/评估结果将被标记为排除（保审计），报告聚合将重算剔除该用例。'
  }
}

/** 确认文案构建（§5.3/§5.8/§5.9/§5.10 逐字；暂停/继续/恢复对齐旧 Vue BASIC_CONFIRM） */
export function buildTaskConfirmCopy(state: TaskConfirmState): {
  title: string
  desc: string
  confirmText: string
  destructive: boolean
} {
  switch (state.kind) {
    case 'row-delete':
      return {
        title: '删除任务',
        desc: '将把 1 个任务移入回收站，可在回收站恢复。',
        confirmText: '删除',
        destructive: true,
      }
    case 'batch-delete':
      return {
        title: '批量删除任务',
        desc: `将把 ${state.tasks.length} 个任务移入回收站，可在回收站恢复。`,
        confirmText: '删除',
        destructive: true,
      }
    case 'row-purge':
      return {
        title: '彻底删除',
        desc: '将永久删除 1 个任务及其全部执行数据，此操作不可恢复。',
        confirmText: '彻底删除',
        destructive: true,
      }
    case 'batch-purge':
      return {
        title: '批量彻底删除',
        desc: `将永久删除 ${state.tasks.length} 个任务及其全部执行数据，此操作不可恢复。`,
        confirmText: '彻底删除',
        destructive: true,
      }
    case 'row-restore':
      return {
        title: '恢复任务',
        desc: '确定要恢复该任务吗？',
        confirmText: '恢复',
        destructive: false,
      }
    case 'batch-restore':
      return {
        title: '批量恢复任务',
        desc: `确定要恢复选中的 ${state.tasks.length} 个任务吗？`,
        confirmText: '恢复',
        destructive: false,
      }
    case 'row-stop':
    case 'detail-stop':
      return {
        title: '停止任务',
        desc: '确定要停止该任务吗？',
        confirmText: '停止',
        destructive: true,
      }
    case 'row-pause':
      return {
        title: '暂停任务',
        desc: '确定要暂停该测试任务吗？',
        confirmText: '暂停',
        destructive: false,
      }
    case 'row-resume':
      return {
        title: '继续任务',
        desc: '确定要继续该测试任务吗？',
        confirmText: '继续',
        destructive: false,
      }
    case 'detail-control':
      return state.action === 'pause'
        ? {
            title: '暂停任务',
            desc: '确定要暂停该测试任务吗？',
            confirmText: '暂停',
            destructive: false,
          }
        : {
            title: '继续任务',
            desc: '确定要继续该测试任务吗？',
            confirmText: '继续',
            destructive: false,
          }
    case 'batch-publish':
      return {
        title: '批量发布',
        desc: `将为选中的 ${state.tasks.length} 个任务发布（名称沿用源任务名，不可发布状态自动跳过）。是否继续？`,
        confirmText: '发布',
        destructive: false,
      }
    case 'remove-case':
      return {
        title: '移除用例',
        desc: buildCaseRemoveDesc(state.phase),
        confirmText: '移除',
        destructive: true,
      }
  }
}

export function TaskConfirmDialog({
  open,
  state,
  onOpenChange,
  isLoading,
  onConfirm,
}: {
  open: boolean
  state: TaskConfirmState | null
  onOpenChange: (open: boolean) => void
  isLoading?: boolean
  onConfirm: () => void
}) {
  if (!state) return null
  const copy = buildTaskConfirmCopy(state)
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={copy.title}
      desc={copy.desc}
      confirmText={copy.confirmText}
      destructive={copy.destructive}
      isLoading={isLoading}
      handleConfirm={onConfirm}
    />
  )
}
