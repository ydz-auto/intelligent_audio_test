/**
 * 任务行操作菜单（09_任务域.md §3.6.2 DataTableRowActionMenu）。
 * 按状态显隐 + 权限隐藏（对齐现 taskActions 口径）；控制类操作进行中置灰。
 * 重新执行/重新评估经 onReexecute 打开 §5.7 范围选择弹窗；未传时回落 toast 演示。
 * INT-932 接线：删除/收藏/恢复/彻底删除/暂停/继续/停止经 useTaskActions
 * （infrastructure/api/tasks-actions-api + tasks-control-api）发真实请求，成功后列表刷新。
 * INT-949：危险/控制操作（删除/彻底删除/恢复/暂停/继续/停止）点击先弹 ConfirmDialog
 * （§5.8/§5.10 + 旧 Vue 基线），确认才发请求，取消不发请求。
 */
import { useNavigate } from '@tanstack/react-router'
import { MoreHorizontal, Star } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskActions } from '@/application/tasks/use-task-actions'
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
import type { TaskListItem } from '@/domain/models/task'
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
    items.push({
      key: 'report',
      label: '查看报告',
      disabled: !task.reports?.count,
      disabledReason: task.reports?.count ? undefined : '该任务暂无报告',
      onSelect: () => toast.success('报告页随报告域卡 INT-360 落地'),
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
      onSelect: () => toast.success('报告生成成功'),
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
  const actions = useTaskActions()

  const items = buildDailyItems(task, hasPermission, {
    goDetail: () => void navigate({ to: '/tasks/$tab', params: { tab: String(task.id) } }),
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

  const mutating = [
    actions.remove,
    actions.favorite,
    actions.unfavorite,
    actions.restore,
    actions.purge,
    actions.control,
    actions.stop,
  ].some((m) => m.isPending)

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
    </>
  )
}
