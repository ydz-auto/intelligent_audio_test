/**
 * 任务行操作菜单（09_任务域.md §3.6.2 DataTableRowActionMenu）。
 * 按状态显隐 + 权限隐藏（对齐现 taskActions 口径）；控制类操作进行中置灰。
 * 重新执行/重新评估经 onReexecute 打开 §5.7 范围选择弹窗；未传时回落 toast 演示。
 * INT-932 接线：删除/收藏/恢复/彻底删除/暂停/继续/停止经 useTaskActions
 * （infrastructure/api/tasks-actions-api + tasks-control-api）发真实请求，成功后列表刷新。
 * INT-949：危险/控制操作（删除/彻底删除/恢复/暂停/继续/停止）点击先弹 ConfirmDialog
 * （§5.8/§5.10 + 旧 Vue 基线），确认才发请求，取消不发请求。
 * INT-967：查看报告跳 /report/:id（task.reports.reports[0].id）；重新生成报告接真实
 * generateTaskReport + regenerateReport（§3.6.2，对齐旧 Vue regenerateReport：定位已有报告 →
 * 有旧报告弹「将删除当前报告并重新生成」确认 → regenerate → 跳报告页），不再 toast 假成功。
 */
import { useNavigate } from '@tanstack/react-router'
import { MoreHorizontal, Star } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskActions } from '@/application/tasks/use-task-actions'
import { waitForReportGenerated } from '@/application/reports/use-report-compare'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { TaskListItem } from '@/domain/models/task'
import { generateTaskReport, regenerateReport } from '@/infrastructure/api/reports-api'
import {
  TaskConfirmDialog,
  type TaskConfirmState,
} from '@/features/tasks/components/task-confirm-dialogs'

type MenuItem = {
  key: string
  label: string
  permission?: string
  destructive?: boolean
  disabled?: boolean
  disabledReason?: string
  onSelect?: () => void
}

const TERMINAL_STATES = new Set(['completed', 'failed', 'stopped', 'merged', 'skipped'])
const ACTIVE_STATES = new Set(['running', 'paused', 'queued'])

export type ReexecuteActionType = 'retry' | 'reevaluate'

function buildDailyItems(
  task: TaskListItem,
  has: (p: string) => boolean,
  actions: {
    goDetail: () => void
    goReport: () => void
    onRegenReport: (task: TaskListItem) => void
    onQuickView: () => void
    onPublish: () => void
    onReexecute: (task: TaskListItem, actionType: ReexecuteActionType) => void
    onDelete: () => void
    onFavorite: () => void
    onUnfavorite: () => void
    onRestore: () => void
    onPurge: () => void
    onPause: () => void
    onResume: () => void
    onStop: () => void
  }
): MenuItem[] {
  const items: MenuItem[] = []

  if (has('task:read')) {
    items.push(
      { key: 'detail', label: '查看详情', onSelect: actions.goDetail },
      { key: 'quick-view', label: '快速查看', onSelect: actions.onQuickView }
    )
  }
  if (has('report:read')) {
    // §3.6.2 查看报告（report:read）：跳 /report/:id（task.reports.reports[0].id）；无报告禁用
    items.push({
      key: 'report',
      label: '查看报告',
      disabled: !task.reports?.count,
      disabledReason: task.reports?.count ? undefined : '该任务暂无报告',
      onSelect: actions.goReport,
    })
  }
  if (has('task:read') && !task.deleted) {
    items.push({
      key: 'favorite',
      label: task.is_favorite ? '取消收藏' : '收藏',
      onSelect: task.is_favorite ? actions.onUnfavorite : actions.onFavorite,
    })
  }
  if (has('report:create') && TERMINAL_STATES.has(task.execution_status ?? '')) {
    items.push({
      key: 'regen-report',
      label: '重新生成报告',
      onSelect: () => actions.onRegenReport(task),
    })
  }
  if (has('task:execute')) {
    if (ACTIVE_STATES.has(task.execution_status ?? '')) {
      if (task.execution_status === 'running' || task.execution_status === 'paused') {
        items.push({
          key: 'pause',
          label: task.execution_status === 'running' ? '暂停' : '继续',
          onSelect: task.execution_status === 'running' ? actions.onPause : actions.onResume,
        })
      }
      if (task.execution_status === 'running' || task.execution_status === 'paused' || task.execution_status === 'queued') {
        items.push({
          key: 'stop',
          label: '停止',
          destructive: true,
          onSelect: actions.onStop,
        })
      }
    }
    if (
      task.execution_status === 'pending' ||
      task.execution_status === 'failed' ||
      task.execution_status === 'completed' ||
      task.execution_status === 'stopped'
    ) {
      items.push({
        key: 'rerun',
        label: '重新执行',
        onSelect: () => actions.onReexecute(task, 'retry'),
      })
    }
  }
  if (has('evaluation:execute') && TERMINAL_STATES.has(task.execution_status ?? '')) {
    items.push({
      key: 'reevaluate',
      label: '重新评估',
      onSelect: () => actions.onReexecute(task, 'reevaluate'),
    })
  }
  if (has('task:publish')) {
    items.push({
      key: 'publish',
      label: '发布',
      disabled: !['completed', 'failed', 'stopped', 'pending'].includes(task.execution_status ?? ''),
      disabledReason: '仅已完成/失败/停止/待执行状态可发布',
      onSelect: actions.onPublish,
    })
  }

  if (task.deleted) {
    if (has('task:delete')) {
      items.push(
        {
          key: 'restore',
          label: '恢复',
          onSelect: actions.onRestore,
        },
        {
          key: 'purge',
          label: '彻底删除',
          destructive: true,
          onSelect: actions.onPurge,
        }
      )
    }
  } else if (has('task:delete')) {
    items.push({
      key: 'delete',
      label: '删除',
      destructive: true,
      onSelect: actions.onDelete,
    })
  }

  return items
}

export function TaskRowActions({
  task,
  onQuickView,
  onPublish,
  onReexecute,
}: {
  task: TaskListItem
  onQuickView: (task: TaskListItem) => void
  onPublish?: (task: TaskListItem) => void
  /** 重新执行/重新评估 → §5.7 范围选择弹窗 */
  onReexecute: (task: TaskListItem, actionType: ReexecuteActionType) => void
}) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const [isControlling, setIsControlling] = useState(false)
  const [confirm, setConfirm] = useState<TaskConfirmState | null>(null)
  const [confirmPending, setConfirmPending] = useState(false)
  /** 重新生成报告覆盖确认（§3.6.2：任务已有报告 → 弹「将删除当前报告并重新生成」确认） */
  const [regenConfirm, setRegenConfirm] = useState<{ task: TaskListItem; reportId: number } | null>(null)
  const [regenPending, setRegenPending] = useState(false)
  const actions = useTaskActions()

  const items = buildDailyItems(task, hasPermission, {
    goDetail: () => void navigate({ to: '/tasks/$tab', params: { tab: String(task.id) } }),
    goReport: () => {
      const reportId = task.reports?.reports[0]?.id
      if (reportId != null) {
        void navigate({ to: '/report/$reportId', params: { reportId: String(reportId) } })
      }
    },
    onRegenReport: (t) => void handleRegenReport(t),
    onQuickView: () => onQuickView(task),
    onPublish: () =>
      onPublish ? onPublish(task) : toast.success('发布流程见发布任务弹窗'),
    onReexecute,
    onDelete: () => setConfirm({ kind: 'row-delete', task }),
    onFavorite: () => actions.favorite.mutate(task.id),
    onUnfavorite: () => actions.unfavorite.mutate(task.id),
    onRestore: () => setConfirm({ kind: 'row-restore', task }),
    onPurge: () => setConfirm({ kind: 'row-purge', task }),
    onPause: () => setConfirm({ kind: 'row-pause', task }),
    onResume: () => setConfirm({ kind: 'row-resume', task }),
    onStop: () => setConfirm({ kind: 'row-stop', task }),
  })

  /** 确认后才发请求（INT-949）；失败 toast 由 mutation onError 处理，弹窗保留可重试 */
  const handleConfirm = async () => {
    if (!confirm) return
    setConfirmPending(true)
    try {
      switch (confirm.kind) {
        case 'row-delete':
          await actions.remove.mutateAsync(confirm.task.id)
          break
        case 'row-purge':
          await actions.purge.mutateAsync(confirm.task.id)
          break
        case 'row-restore':
          await actions.restore.mutateAsync(confirm.task.id)
          break
        case 'row-stop':
          await actions.stop.mutateAsync(confirm.task.id)
          break
        case 'row-pause':
          await actions.control.mutateAsync({ taskId: confirm.task.id, action: 'pause' })
          break
        case 'row-resume':
          await actions.control.mutateAsync({ taskId: confirm.task.id, action: 'resume' })
          break
        default:
          return
      }
      setConfirm(null)
    } catch {
      // mutation onError 已 toast
    } finally {
      setConfirmPending(false)
    }
  }

  /**
   * §3.6.2 重新生成报告（对齐旧 Vue regenerateReport，INT-967 接线）：
   * generateTaskReport 定位已有报告（任务已有 → { id, status:'exists' }；无 → 异步生成
   * { taskId, status:'generating' }）→ 有旧报告弹覆盖确认，无旧报告等 SSE 回传后跳报告页。
   * 先订阅 report_generated、等 SSE open 再 POST（对齐二次对比 onOpen-gate 防快速失败竞态）。
   */
  const handleRegenReport = async (locateTask: TaskListItem) => {
    const controller = new AbortController()
    let sseOpened: (() => void) | undefined
    const sseReady = new Promise<void>((resolve) => {
      sseOpened = resolve
    })
    const waitPromise = waitForReportGenerated(
      { taskId: locateTask.id },
      { signal: controller.signal, onOpen: () => sseOpened?.() }
    )
    // 交接前先挂 no-op catch，避免取消/超时成为 unhandled rejection
    void waitPromise.catch(() => undefined)
    try {
      // 等 SSE 连接建立（≤2s 兜底）再提交，杜绝 <1s 快速失败事件早于订阅到达的竞态
      await Promise.race([sseReady, new Promise((r) => setTimeout(r, 2_000))])
      const result = await generateTaskReport({
        task_id: locateTask.id,
        name: `${locateTask.name || `任务${locateTask.id}`} - 测试报告`,
        description: locateTask.description ?? undefined,
      })
      if (result.status === 'exists' && result.id !== undefined) {
        // 任务已有报告 → 取消本次预订阅（未发起生成），弹「将删除当前报告并重新生成」确认
        controller.abort()
        setRegenConfirm({ task: locateTask, reportId: result.id })
        return
      }
      // 无旧报告 → 异步生成中：loading toast + 等 SSE report_generated 回传真实 report_id 后跳报告页
      const loadingId = toast.loading('正在生成报告，请稍候...')
      try {
        const reportId = await waitPromise
        toast.dismiss(loadingId)
        toast.success('报告生成成功')
        void navigate({ to: '/report/$reportId', params: { reportId: String(reportId) } })
      } catch (waitError) {
        toast.dismiss(loadingId)
        toast.error(waitError instanceof Error ? waitError.message : '报告生成失败，请稍后重试')
      }
    } catch (error) {
      controller.abort()
      toast.error(error instanceof Error ? error.message : '报告生成失败，请稍后重试')
    }
  }

  /** 重新生成报告覆盖确认（确认后 POST /reports/{id}/regenerate → 等 SSE → 跳报告页） */
  const handleRegenConfirm = async () => {
    if (!regenConfirm) return
    setRegenPending(true)
    const { task: regenTask, reportId: existingReportId } = regenConfirm
    const controller = new AbortController()
    let sseOpened: (() => void) | undefined
    const sseReady = new Promise<void>((resolve) => {
      sseOpened = resolve
    })
    const waitPromise = waitForReportGenerated(
      { taskId: regenTask.id },
      { signal: controller.signal, onOpen: () => sseOpened?.() }
    )
    void waitPromise.catch(() => undefined)
    try {
      await Promise.race([sseReady, new Promise((r) => setTimeout(r, 2_000))])
      await regenerateReport(existingReportId)
      const loadingId = toast.loading('正在重新生成报告，请稍候...')
      try {
        const newReportId = await waitPromise
        toast.dismiss(loadingId)
        toast.success('报告重新生成成功')
        setRegenConfirm(null)
        void navigate({ to: '/report/$reportId', params: { reportId: String(newReportId) } })
      } catch (waitError) {
        toast.dismiss(loadingId)
        toast.error(waitError instanceof Error ? waitError.message : '报告重新生成失败，请稍后重试')
      }
    } catch (error) {
      controller.abort()
      toast.error(error instanceof Error ? error.message : '报告重新生成失败，请稍后重试')
    } finally {
      setRegenPending(false)
    }
  }

  const mutating =
    [
      actions.remove,
      actions.favorite,
      actions.unfavorite,
      actions.restore,
      actions.purge,
      actions.control,
      actions.stop,
    ].some((m) => m.isPending) || regenPending

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant='ghost'
              size='icon-sm'
              aria-label='任务操作'
              disabled={isControlling || mutating}
            />
          }
        >
          <MoreHorizontal aria-hidden='true' />
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end' className='w-44'>
          <DropdownMenuGroup>
            <DropdownMenuLabel className='truncate'>{task.name}</DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          {items.map((item) => (
            <DropdownMenuItem
              key={item.key}
              disabled={item.disabled || mutating}
              data-variant={item.destructive ? 'destructive' : undefined}
              onSelect={() => {
                setIsControlling(true)
                setTimeout(() => setIsControlling(false), 600)
                item.onSelect?.()
              }}
            >
              {item.key === 'favorite' && task.is_favorite ? (
                <Star aria-hidden='true' className='size-4 fill-current' />
              ) : null}
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      {/* 行操作确认（INT-949：删除/彻底删除/恢复/暂停/继续/停止，取消不发请求） */}
      <TaskConfirmDialog
        open={confirm != null}
        state={confirm}
        onOpenChange={(open) => !open && setConfirm(null)}
        isLoading={confirmPending}
        onConfirm={() => void handleConfirm()}
      />
      {/* §3.6.2 重新生成报告覆盖确认（INT-967：任务已有报告 → 确认后 regenerate → 跳报告页；
          取消/关闭弹窗 → 跳旧报告，对齐旧 Vue cancelText『查看旧报告』） */}
      <ConfirmDialog
        open={regenConfirm != null}
        onOpenChange={(open) => {
          if (!open && regenConfirm && !regenPending) {
            const oldReportId = regenConfirm.reportId
            setRegenConfirm(null)
            void navigate({ to: '/report/$reportId', params: { reportId: String(oldReportId) } })
          }
        }}
        title='重新生成报告'
        desc='将删除当前报告并重新生成，旧报告数据将被覆盖。是否继续？'
        confirmText='重新生成'
        cancelBtnText='查看旧报告'
        isLoading={regenPending}
        handleConfirm={() => void handleRegenConfirm()}
      />
    </>
  )
}
