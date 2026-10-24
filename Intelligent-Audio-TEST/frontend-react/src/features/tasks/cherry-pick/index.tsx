/**
 * 挑选合并页签（18_挑选合并交互重设计.md §2.3/§2.2，INT-600）。
 * 统一合并容器列表（整任务合并 ∪ 结果挑选，§11-1 落地前客户端合并）+ 合并方式 facet +
 * stats 徽章行 + 开始挑选（页内四步向导，替换列表区）/打开购物车/管理挑选集。
 * 旧「合并」页签收编本页（§2.2 裁定①）；algo_engineer 列表只读可见、挑选链整链隐藏（§8）。
 */
import { Plus, RefreshCw, ShoppingCart } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import {
  useCherryPickContainers,
} from '@/application/tasks/cherry-pick/use-cherry-pick-containers'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { CherryPickContainer } from '@/domain/models/cherryPick'
import { containerMixState } from '@/domain/lib/container-composition'
import {
  formatPickDateTime,
  MERGE_TYPE_LABELS,
} from '@/features/tasks/cherry-pick/constants'
import {
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
} from '@/features/tasks/constants'
import { CartDrawer } from '@/features/tasks/cherry-pick/components/cart-drawer'
import { MergeTypeFacet } from '@/features/tasks/cherry-pick/components/merge-type-facet'
import { PickSetPopover } from '@/features/tasks/cherry-pick/components/pick-set-popover'
import { SourceTraceRow } from '@/features/tasks/cherry-pick/components/source-trace-row'
import { CherryPickWizard } from '@/features/tasks/cherry-pick/cherry-pick-wizard'
import type { WizardStepKey } from '@/features/tasks/cherry-pick/constants'
import type { WizardState } from '@/features/tasks'

export function CherryPickTab({
  wizard,
  onWizardOpen,
  onWizardClose,
}: {
  /** 页级向导状态（批量「加入挑选」跨页签进入；本页「开始挑选」也经此开） */
  wizard: WizardState | null
  onWizardOpen: (step: WizardStepKey, taskIds?: number[]) => void
  onWizardClose: () => void
}) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const cartCount = usePickCartStore((s) => s.total)

  const [search, setSearch] = useState('')
  const [mergeType, setMergeType] = useState<'all' | 'whole' | 'picked'>('all')
  const [cartOpen, setCartOpen] = useState(false)

  // 挂载即拉取购物车镜像 + 挑选集（§6.3 同步点：角标/页签计数数据源）
  useEffect(() => {
    void usePickCartStore.getState().refreshCart()
    void usePickCartStore.getState().refreshPickSets()
  }, [])

  const containersQuery = useCherryPickContainers({
    search: search.trim() || undefined,
    mergeType,
  })
  const containers = containersQuery.data?.items ?? []
  const canWrite = hasPermission('task:cherry_pick')

  const stats = useMemo(() => {
    let whole = 0
    let picked = 0
    for (const c of containers) {
      if (c.mergeType === 'whole') whole += 1
      else picked += 1
    }
    return { total: containers.length, whole, picked }
  }, [containers])

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      {/* 页签 Actions */}
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex flex-wrap items-center gap-2'>
          <MergeTypeFacet value={mergeType} onChange={setMergeType} />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder='搜索名称/描述'
            className='h-7 w-40 text-[0.8rem]'
            aria-label='搜索名称/描述'
          />
          <div className='flex flex-wrap items-center gap-1.5 text-xs'>
            <Badge variant='secondary' className='font-mono text-[10px]'>
              合并容器 {stats.total}
            </Badge>
            <Badge variant='outline' className='font-mono text-[10px]'>
              整任务合并 {stats.whole}
            </Badge>
            <Badge variant='outline' className='font-mono text-[10px]'>
              结果挑选 {stats.picked}
            </Badge>
          </div>
        </div>
        <div className='flex flex-wrap items-center gap-2'>
          {canWrite && (
            <Button size='sm' className='h-8 gap-1.5' onClick={() => onWizardOpen('pick')}>
              <Plus aria-hidden='true' className='size-3.5' />
              开始挑选
            </Button>
          )}
          {hasPermission('task:read') && (
            <Button
              size='sm'
              variant='outline'
              className='h-8 gap-1.5'
              onClick={() => setCartOpen(true)}
            >
              <ShoppingCart aria-hidden='true' className='size-3.5' />
              打开购物车
              {cartCount > 0 && (
                <Badge className='ml-0.5 rounded-lg px-1.5 font-normal'>{cartCount}</Badge>
              )}
            </Button>
          )}
          <PickSetPopover />
        </div>
      </div>

      {/* 列表 ↔ 向导切换 */}
      {wizard != null ? (
        <CherryPickWizard
          open
          step={wizard.step}
          onStepChange={(step) => onWizardOpen(step, wizard.taskIds)}
          onClose={onWizardClose}
          presetTaskIds={wizard.taskIds}
        />
      ) : containersQuery.isLoading ? (
        <div className='rounded-xl border'>
          <Skeleton className='h-10 w-full rounded-none border-b' />
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
          ))}
        </div>
      ) : containersQuery.isError ? (
        <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
          <Empty className='h-[400px]'>
            <EmptyMedia variant='icon'>
              <RefreshCw aria-hidden='true' className='size-4' />
            </EmptyMedia>
            <EmptyHeader>
              <EmptyTitle>挑选合并任务加载失败</EmptyTitle>
              <EmptyDescription>请检查网络或后端服务后重试</EmptyDescription>
              <EmptyContent>
                <Button variant='outline' size='sm' onClick={() => containersQuery.refetch()}>
                  重试
                </Button>
              </EmptyContent>
            </EmptyHeader>
          </Empty>
        </div>
      ) : containers.length === 0 ? (
        <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
          <Empty className='h-[400px]'>
            <EmptyMedia variant='icon'>
              <ShoppingCart aria-hidden='true' />
            </EmptyMedia>
            <EmptyHeader>
              <EmptyTitle>暂无挑选合并任务</EmptyTitle>
              <EmptyDescription>
                点击「开始挑选」，从任务/用例/设备/结果类型任一层级勾选执行结果，加入购物车后复核合并
              </EmptyDescription>
            </EmptyHeader>
            {canWrite && (
              <EmptyDescription>
                <Button
                  variant='link'
                  size='sm'
                  className='h-7'
                  onClick={() => onWizardOpen('pick')}
                >
                  开始挑选
                </Button>
              </EmptyDescription>
            )}
          </Empty>
        </div>
      ) : (
        <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[860px] text-[13px]'>
              <thead>
                <tr className='bg-[var(--table-header)] text-xs'>
                  <th className='w-9 px-3 py-2 text-left font-medium'>☑ 选择</th>
                  <th className='px-3 py-2 text-left font-medium'>任务名称</th>
                  <th className='px-3 py-2 text-left font-medium'>合并方式</th>
                  <th className='px-3 py-2 text-left font-medium'>执行状态</th>
                  <th className='px-3 py-2 text-left font-medium'>评估状态</th>
                  <th className='px-3 py-2 text-left font-medium'>用例数</th>
                  <th className='px-3 py-2 text-left font-medium'>来源</th>
                  <th className='px-3 py-2 text-left font-medium'>创建时间</th>
                  <th className='w-28 px-3 py-2 text-right font-medium'>操作</th>
                </tr>
              </thead>
              <tbody>
                {containers.map((container) => (
                  <ContainerRow
                    key={container.id}
                    container={container}
                    onQuickView={(c) =>
                      void navigate({ to: '/tasks/$tab', params: { tab: String(c.id) } })
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <CartDrawer
        open={cartOpen}
        onOpenChange={setCartOpen}
        onGoReview={() => onWizardOpen('review')}
      />
    </div>
  )
}

function ContainerRow({
  container,
  onQuickView,
}: {
  container: CherryPickContainer
  onQuickView: (container: CherryPickContainer) => void
}) {
  const { hasPermission } = usePermissions()
  const execMeta = getExecutionStatusMeta(container.executionStatus)
  const evalMeta = getEvaluationStatusMeta(container.evaluationStatus)
  const mergeLabel = MERGE_TYPE_LABELS[container.mergeType]
  const sourceDesc = `来源 ${container.sourceTaskCount} 个任务 · 结果 ${container.sourceResultCount} 条`
  // §5.5.4 列表执行状态列：混态（0 < failed_cases < case_count）显示「部分失败」，
  // 纯前端展示映射，后端字符串仍为 failed；无失败 / 计数缺失 → 沿用原状态徽章。
  const mixState = containerMixState(container.failedCases, container.caseCount)

  return (
    <>
      <tr className='hover:bg-muted/40 border-border/60 border-b transition-colors'>
        <td className='px-3 py-2'>
          <Checkbox
            aria-label={`选择合并容器「${container.name}」`}
            title='容器级批量操作待接线'
            disabled
            className='opacity-40'
          />
        </td>
        <td className='max-w-64 px-3 py-2'>
          <span className='flex items-center gap-1.5 truncate font-medium'>
            {container.isFavorite && (
              <span className='text-warning size-3 shrink-0 fill-current'>★</span>
            )}
            {container.name}
          </span>
          <span className='text-muted-foreground block truncate text-xs'>
            {sourceDesc}
          </span>
        </td>
        <td className='px-3 py-2'>
          <Badge variant={container.mergeType === 'whole' ? 'secondary' : 'outline'}>
            {mergeLabel}
          </Badge>
        </td>
        <td className='px-3 py-2'>
          {mixState === 'partial' ? (
            <StatusBadge
              variant='warning'
              title={`部分失败 ${container.failedCases}/${container.caseCount}`}
            >
              <span
                className='bg-warning size-1.5 shrink-0 rounded-full'
                aria-hidden='true'
              />
              <span className='min-w-0 truncate leading-normal'>部分失败</span>
            </StatusBadge>
          ) : (
            <StatusBadge label={execMeta.label} variant={execMeta.variant} />
          )}
        </td>
        <td className='px-3 py-2'>
          <StatusBadge
            label={evalMeta.label}
            variant={evalMeta.variant}
            pulse={evalMeta.pulse}
          />
        </td>
        <td className='px-3 py-2 font-mono tabular-nums'>
          {container.totalCases ?? '—'}
        </td>
        <td className='px-3 py-2 font-mono text-xs tabular-nums'>
          {container.sourceTaskCount}
        </td>
        <td className='px-3 py-2 font-mono text-xs whitespace-nowrap tabular-nums'>
          {formatPickDateTime(container.createdAt)}
        </td>
        <td className='px-3 py-2 text-right'>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant='ghost' size='icon-sm' aria-label='挑选合并任务操作' />}
            >
              <span className='text-lg leading-none'>⋯</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align='end' className='w-40'>
              <DropdownMenuGroup>
                <DropdownMenuLabel className='truncate'>{container.name}</DropdownMenuLabel>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => onQuickView(container)}>
                查看详情
              </DropdownMenuItem>
              {hasPermission('report:read') && (
                <DropdownMenuItem onSelect={() => toast.success('报告页随报告域卡落地')}>
                  查看报告
                </DropdownMenuItem>
              )}
              {hasPermission('report:create') && (
                <DropdownMenuItem onSelect={() => toast.success('报告生成成功')}>
                  生成报告（手动）
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
              {hasPermission('task:update') && (
                <DropdownMenuItem onSelect={() => toast.success('重命名流程见任务详情')}>
                  重命名
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
      <tr className='border-border/60 border-b'>
        <td colSpan={9}>
          <SourceTraceRow container={container} />
        </td>
      </tr>
    </>
  )
}
