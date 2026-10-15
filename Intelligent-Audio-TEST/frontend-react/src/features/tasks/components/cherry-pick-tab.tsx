/**
 * 挑选合并页签（09_任务域.md §3.9，第四页签）。
 * 文案红线：站内一律「挑选合并/挑选/加入购物车/购物车/下单/挑选集」，不出现 Cherry-Pick。
 * Actions：主按钮「打开购物车」（ShoppingCart + 条目数 Badge）→ 购物车 Drawer；
 * 次按钮「管理挑选集」（ghost，Popover：恢复进购物车/删除）。
 * 表格列：名称（次行说明）/执行状态/评估状态/用例数/来源任务数（Tooltip 展开来源 #id）/
 * 创建时间/操作（查看详情/查看报告/生成报告/发布/收藏/删除）。
 */
import { useNavigate } from '@tanstack/react-router'
import { MoreHorizontal, ShoppingCart, Star } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useCartStore } from '@/application/tasks/use-cart-store'
import { Badge } from '@/components/ui/badge'
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
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { CherryPickTask } from '@/domain/models/task'
import {
  formatDateTime,
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
} from '@/features/tasks/constants'
import { CartDrawer } from '@/features/tasks/components/cart-drawer'

function SourceCountCell({ ids }: { ids: number[] }) {
  return (
    <Tooltip>
      <TooltipTrigger render={<span className='font-mono text-xs tabular-nums'>{ids.length}</span>} />
      <TooltipContent>
        来源任务：{ids.map((id) => `#${id}`).join('、')}
      </TooltipContent>
    </Tooltip>
  )
}

function PickSetMenu() {
  const { pickSets, restorePickSet, deletePickSet } = useCartStore()
  const [open, setOpen] = useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant='ghost' size='sm' className='h-8 gap-1.5 px-2.5' />
        }
      >
        管理挑选集
      </PopoverTrigger>
      <PopoverContent align='end' className='min-w-56 p-1.5'>
        {pickSets.length === 0 ? (
          <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
            暂无挑选集
          </p>
        ) : (
          pickSets.map((set) => (
            <div
              key={set.id}
              className='hover:bg-accent flex items-center gap-2 rounded-md px-2 py-1.5'
            >
              <div className='min-w-0 flex-1'>
                <p className='truncate text-sm font-medium'>{set.name}</p>
                <p className='text-muted-foreground text-xs tabular-nums'>
                  {set.entries.length} 条 · {formatDateTime(set.createdAt)}
                </p>
              </div>
              <Button
                variant='ghost'
                size='xs'
                className='h-6 px-2 text-xs'
                onClick={() => {
                  restorePickSet(set.id)
                  toast.success('已恢复到购物车')
                }}
              >
                恢复
              </Button>
              <Button
                variant='ghost'
                size='xs'
                className='text-destructive hover:text-destructive h-6 px-2 text-xs'
                onClick={() => deletePickSet(set.id)}
              >
                删除
              </Button>
            </div>
          ))
        )}
      </PopoverContent>
    </Popover>
  )
}

export function CherryPickTab({
  tasks,
  loading,
}: {
  tasks: CherryPickTask[]
  loading: boolean
}) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const cartCount = useCartStore((s) => s.entries.length)
  const [cartOpen, setCartOpen] = useState(false)

  if (loading) {
    return (
      <div className='rounded-xl border'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  return (
    <div className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div />
        <div className='flex flex-wrap items-center gap-2'>
          <PickSetMenu />
          {hasPermission('task:read') && (
            <Button size='sm' className='h-8 gap-1.5' onClick={() => setCartOpen(true)}>
              <ShoppingCart aria-hidden='true' className='size-3.5' />
              打开购物车
              {cartCount > 0 && (
                <Badge className='ml-0.5 rounded-lg px-1.5 font-normal'>{cartCount}</Badge>
              )}
            </Button>
          )}
        </div>
      </div>

      {tasks.length === 0 ? (
        <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
          <Empty className='h-[400px]'>
            <EmptyMedia variant='icon'>
              <ShoppingCart aria-hidden='true' />
            </EmptyMedia>
            <EmptyHeader>
              <EmptyTitle>暂无挑选合并任务</EmptyTitle>
              <EmptyDescription>
                从任务详情或对比报告勾选执行结果「加入购物车」，再下单合并
              </EmptyDescription>
            </EmptyHeader>
            <EmptyDescription>
              <Button variant='link' size='sm' className='h-7' onClick={() => toast.success('使用手册锚点随文档域卡落位')}>
                了解挑选合并
              </Button>
            </EmptyDescription>
          </Empty>
        </div>
      ) : (
        <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[820px] text-[13px]'>
              <thead>
                <tr className='bg-[var(--table-header)] text-xs'>
                  <th className='px-3 py-2 text-left font-medium'>名称</th>
                  <th className='px-3 py-2 text-left font-medium'>执行状态</th>
                  <th className='px-3 py-2 text-left font-medium'>评估状态</th>
                  <th className='px-3 py-2 text-left font-medium'>用例数</th>
                  <th className='px-3 py-2 text-left font-medium'>来源任务数</th>
                  <th className='px-3 py-2 text-left font-medium'>创建时间</th>
                  <th className='w-28 px-3 py-2 text-right font-medium'>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => {
                  const execMeta = getExecutionStatusMeta(task.execution_status)
                  const evalMeta = getEvaluationStatusMeta(task.evaluation_status)
                  return (
                    <tr
                      key={task.id}
                      className='hover:bg-muted/40 border-border/60 border-b transition-colors'
                    >
                      <td className='max-w-64 px-3 py-2'>
                        <span className='flex items-center gap-1.5 font-medium truncate'>
                          {task.is_favorite && (
                            <Star aria-hidden='true' className='text-warning size-3 shrink-0 fill-current' />
                          )}
                          {task.name}
                        </span>
                        <span className='text-muted-foreground block truncate'>
                          {task.description ?? ''}
                        </span>
                      </td>
                      <td className='px-3 py-2'>
                        <StatusBadge label={execMeta.label} variant={execMeta.variant} />
                      </td>
                      <td className='px-3 py-2'>
                        <StatusBadge
                          label={evalMeta.label}
                          variant={evalMeta.variant}
                          pulse={evalMeta.pulse}
                        />
                      </td>
                      <td className='px-3 py-2 font-mono tabular-nums'>
                        {task.total_cases ?? '—'}
                      </td>
                      <td className='px-3 py-2'>
                        <SourceCountCell ids={task.source_task_ids} />
                      </td>
                      <td className='px-3 py-2 font-mono text-xs whitespace-nowrap tabular-nums'>
                        {formatDateTime(task.created_at)}
                      </td>
                      <td className='px-3 py-2 text-right'>
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            render={
                              <Button variant='ghost' size='icon-sm' aria-label='挑选合并任务操作' />
                            }
                          >
                            <MoreHorizontal aria-hidden='true' />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align='end' className='w-40'>
                            <DropdownMenuGroup>
                              <DropdownMenuLabel className='truncate'>{task.name}</DropdownMenuLabel>
                            </DropdownMenuGroup>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onSelect={() =>
                                void navigate({ to: '/tasks/$tab', params: { tab: String(task.id) } })
                              }
                            >
                              查看详情
                            </DropdownMenuItem>
                            {hasPermission('report:read') && (
                              <DropdownMenuItem onSelect={() => toast.success('报告页随报告域卡落地')}>
                                查看报告
                              </DropdownMenuItem>
                            )}
                            {hasPermission('report:create') && (
                              <DropdownMenuItem onSelect={() => toast.success('报告生成成功')}>
                                生成报告
                              </DropdownMenuItem>
                            )}
                            {hasPermission('task:publish') && (
                              <DropdownMenuItem onSelect={() => toast.success('发布流程见发布弹窗')}>
                                发布
                              </DropdownMenuItem>
                            )}
                            {hasPermission('task:read') && (
                              <DropdownMenuItem onSelect={() => toast.success('已加入收藏')}>
                                收藏
                              </DropdownMenuItem>
                            )}
                            {hasPermission('task:delete') && (
                              <DropdownMenuItem data-variant='destructive' onSelect={() => toast.success('已移入回收站')}>
                                删除
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <CartDrawer open={cartOpen} onOpenChange={setCartOpen} />
    </div>
  )
}
