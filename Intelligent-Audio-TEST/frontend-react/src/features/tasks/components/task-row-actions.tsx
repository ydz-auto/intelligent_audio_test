/**
 * 任务行操作菜单（09_任务域.md §3.6.2 DataTableRowActionMenu）。
 * 按状态显隐 + 权限隐藏（对齐现 taskActions 口径）；控制类操作进行中置灰。
 * mock 态：动作触发 toast 演示（接线后替换为 application/tasks mutations）。
 */
import { useNavigate } from '@tanstack/react-router'
import { MoreHorizontal, Star } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { TaskListItem } from '@/domain/models/task'

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

function buildDailyItems(
  task: TaskListItem,
  has: (p: string) => boolean,
  actions: { goDetail: () => void; onQuickView: () => void }
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
      onSelect: () => {
        toast.success(task.is_favorite ? '已取消收藏' : '已加入收藏')
        task.is_favorite = !task.is_favorite
      },
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
          onSelect: () => toast.success(task.execution_status === 'running' ? '任务已暂停' : '任务已继续'),
        })
      }
      if (task.execution_status === 'running' || task.execution_status === 'paused' || task.execution_status === 'queued') {
        items.push({
          key: 'stop',
          label: '停止',
          destructive: true,
          onSelect: () => toast.success('任务已停止'),
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
        onSelect: () => toast.success('已发起重新执行'),
      })
    }
  }
  if (has('evaluation:execute') && TERMINAL_STATES.has(task.execution_status ?? '')) {
    items.push({
      key: 'reevaluate',
      label: '重新评估',
      onSelect: () => toast.success('已发起重新评估'),
    })
  }
  if (has('task:publish')) {
    items.push({
      key: 'publish',
      label: '发布',
      disabled: !['completed', 'failed', 'stopped', 'pending'].includes(task.execution_status ?? ''),
      disabledReason: '仅已完成/失败/停止/待执行状态可发布',
      onSelect: () => toast.success('发布流程见发布任务弹窗'),
    })
  }

  if (task.deleted) {
    if (has('task:delete')) {
      items.push(
        {
          key: 'restore',
          label: '恢复',
          onSelect: () => toast.success('已恢复'),
        },
        {
          key: 'purge',
          label: '彻底删除',
          destructive: true,
          onSelect: () => toast.success('已彻底删除'),
        }
      )
    }
  } else if (has('task:delete')) {
    items.push({
      key: 'delete',
      label: '删除',
      destructive: true,
      onSelect: () => toast.success('已移入回收站'),
    })
  }

  return items
}

export function TaskRowActions({
  task,
  onQuickView,
}: {
  task: TaskListItem
  onQuickView: (task: TaskListItem) => void
}) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const [isControlling, setIsControlling] = useState(false)

  const items = buildDailyItems(task, hasPermission, {
    goDetail: () => void navigate({ to: '/tasks/$tab', params: { tab: String(task.id) } }),
    onQuickView: () => onQuickView(task),
  })

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label='任务操作'
            disabled={isControlling}
          />
        }
      >
        <MoreHorizontal aria-hidden='true' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-44'>
        <DropdownMenuLabel className='truncate'>{task.name}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {items.map((item) => (
          <DropdownMenuItem
            key={item.key}
            disabled={item.disabled}
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
  )
}
