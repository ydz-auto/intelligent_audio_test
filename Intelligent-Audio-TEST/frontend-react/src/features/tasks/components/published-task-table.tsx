/**
 * 已发布任务表格（09_任务域.md §3.7：表格 + 展开版本链详情行）。
 * 列：版本/名称·说明/状态/类型/Benchmark/版本数/发布人·发布时间/操作（行内按钮组）。
 * 展开行五个 DetailSection（照 log-detail-layout 键值行）：版本历史 / Benchmark 标记 /
 * 任务详情（发布时冻结）/ 冻结报告 / 执行记录。
 * 数据源：列表 fetchPublishedTaskList（GET /published-tasks）；展开版本链行
 * fetchPublishedTaskDetail（GET /published-tasks/{id}）真实详情。
 */
import { ChevronDown, ChevronRight, Package, RefreshCw, Trophy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { fetchPublishedTaskDetail } from '@/infrastructure/api/tasks-list-api'
import type { PublishedTaskDetail, PublishedTaskItem } from '@/domain/models/task'
import { formatDateTime, getTaskTypeLabel } from '@/features/tasks/constants'

const STATUS_META: Record<string, { label: string; variant: 'success' | 'neutral' }> = {
  published: { label: '已发布', variant: 'success' },
  archived: { label: '已归档', variant: 'neutral' },
}

/** 版本链展开行（§3.7 五节键值行） */
function PublishedExpandRow({ detail }: { detail: PublishedTaskDetail }) {
  const [versionsOpen, setVersionsOpen] = useState(true)
  const [legacy] = useState(!detail.has_task_snapshot)

  return (
    <div className='bg-muted/20 px-4 py-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        {/* ① 版本历史 */}
        <section className='rounded-lg border p-3'>
          <button
            type='button'
            className='flex items-center gap-1 text-sm font-medium'
            onClick={() => setVersionsOpen((v) => !v)}
          >
            <ChevronDown
              aria-hidden='true'
              className={cn('size-4 transition-transform', !versionsOpen && '-rotate-90')}
            />
            版本历史（共 {detail.versions.length} 个版本）
          </button>
          {versionsOpen && (
            <div className='mt-2 flex flex-col gap-1.5'>
              {detail.versions.map((version) => (
                <div
                  key={version.id}
                  className='flex items-center gap-2 text-xs tabular-nums'
                >
                  <span className='font-mono font-medium'>v{version.version}</span>
                  <StatusBadge
                    label={STATUS_META[version.status]?.label ?? version.status}
                    variant={STATUS_META[version.status]?.variant ?? 'neutral'}
                  />
                  {version.is_current && (
                    <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                      当前
                    </Badge>
                  )}
                  <span className='text-muted-foreground'>
                    {formatDateTime(version.published_at)}
                  </span>
                  <span className='text-muted-foreground ml-auto'>
                    来源任务 #{version.source_task_id ?? '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ② Benchmark 标记 */}
        <section className='rounded-lg border p-3'>
          <p className='text-sm font-medium'>Benchmark 标记（发布时冻结）</p>
          {detail.benchmark ? (
            <div className='mt-2 flex flex-col gap-1 text-xs'>
              <span>测试集：{String(detail.snapshot_config.benchmarkSuite ?? '—')}</span>
              <span>被测类别：{String(detail.snapshot_config.benchmarkCategory ?? '—')}</span>
            </div>
          ) : (
            <p className='text-muted-foreground mt-2 text-xs'>该版本未参与 Benchmark 排行</p>
          )}
        </section>
      </div>

      {/* ③ 任务详情（发布时冻结） */}
      <section className='mt-3 rounded-lg border p-3'>
        <p className='text-sm font-medium'>任务详情（发布时冻结 · 不可变）</p>
        {legacy ? (
          <div className='mt-2 rounded-lg border border-warning/40 bg-warning/10 p-2.5 text-xs'>
            历史版本（发布时未冻结任务详情）：任务详情按来源任务当前数据展示，源用例被编辑/删除后可能失真；执行按引用轨还原（源用例需存在）。
          </div>
        ) : (
          <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
            <span className='text-muted-foreground'>来源任务：</span>
            <span className='font-medium'>{detail.source_task_name ?? '—'}</span>
            <Badge variant='outline' className='rounded-md px-1.5'>
              {getTaskTypeLabel(detail.versions[0]?.type ?? null)}
            </Badge>
            <span className='text-muted-foreground'>
              用例 {detail.source_task_completed_cases ?? 0}/{detail.source_task_total_cases ?? 0}
            </span>
            <Button
              size='sm'
              variant='outline'
              className='ml-auto h-7'
              onClick={() => toast.success('冻结任务详情弹窗随 §5.13 冻结族落地')}
            >
              查看冻结任务详情
            </Button>
          </div>
        )}
      </section>

      {/* ④ 冻结报告 */}
      <section className='mt-3 rounded-lg border p-3'>
        <p className='text-sm font-medium'>冻结报告（发布时快照 · 不可变）</p>
        {detail.has_report_snapshot ? (
          <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
            <span className='font-medium'>
              {String(detail.report_snapshot?.name ?? '冻结报告')}
            </span>
            <span className='text-muted-foreground'>
              用例 {String(detail.report_snapshot?.caseCount ?? '—')} · 通过率{' '}
              {String(detail.report_snapshot?.passRate ?? '—')}%
            </span>
            <Button
              size='sm'
              variant='outline'
              className='ml-auto h-7'
              onClick={() => toast.success('冻结报告弹窗随 §5.13 冻结族落地')}
            >
              查看冻结报告
            </Button>
          </div>
        ) : (
          <p className='text-muted-foreground mt-2 text-xs'>
            该版本无冻结报告（发布时源任务无已完成报告）
          </p>
        )}
      </section>

      {/* ⑤ 执行记录 */}
      <section className='mt-3 rounded-lg border p-3'>
        <p className='text-sm font-medium'>执行记录（按冻结快照执行生成的日常任务）</p>
        {detail.execution_history.length > 0 ? (
          <div className='mt-2 flex flex-col gap-1.5 text-xs'>
            {detail.execution_history.map((record) => (
              <div key={record.task_id} className='flex items-center gap-2'>
                <span className='font-medium'>{record.task_name}</span>
                <span className='font-mono'>v{record.version}</span>
                <StatusBadge
                  label={record.status === 'completed' ? '已完成' : record.status}
                  variant={record.status === 'completed' ? 'success' : 'neutral'}
                />
                <span className='text-muted-foreground'>
                  用例 {record.completed_cases}/{record.total_cases}
                </span>
                <span className='text-muted-foreground ml-auto'>
                  {formatDateTime(record.created_at)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className='text-muted-foreground mt-2 text-xs'>该版本暂无执行记录</p>
        )}
      </section>
    </div>
  )
}

export function PublishedTaskTable({
  tasks,
  loading,
  error,
  onRetry,
}: {
  tasks: PublishedTaskItem[]
  loading: boolean
  /** 列表请求失败（P1-3：错误态 + 重试，不再渲染空态） */
  error?: boolean
  onRetry?: () => void
}) {
  const { hasPermission } = usePermissions()
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<PublishedTaskDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  // 展开版本链：取 GET /published-tasks/{id} 真实详情（版本历史/冻结快照/执行记录）
  useEffect(() => {
    if (expandedId == null) {
      setDetail(null)
      setDetailError(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    setDetailError(null)
    fetchPublishedTaskDetail(expandedId)
      .then((d) => {
        if (cancelled) return
        setDetail(d)
        setDetailLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setDetailError(err instanceof Error ? err.message : '已发布任务详情加载失败')
        setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [expandedId])

  if (loading) {
    return (
      <div className='rounded-xl border'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  // P1-3：请求失败渲染错误态 + 重试（不再误示为空态）
  if (error) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <RefreshCw aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>已发布任务列表加载失败</EmptyTitle>
            <EmptyDescription>请检查网络或后端服务后重试</EmptyDescription>
            {onRetry && (
              <EmptyContent>
                <Button variant='outline' size='sm' onClick={onRetry}>
                  重试
                </Button>
              </EmptyContent>
            )}
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <Package aria-hidden='true' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>暂无已发布任务</EmptyTitle>
            <EmptyDescription>
              从日常任务列表发布，沉淀可复用、可追踪的任务资产
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[900px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='w-11 px-3 py-2' />
              <th className='px-3 py-2 text-left font-medium'>版本</th>
              <th className='px-3 py-2 text-left font-medium'>名称/说明</th>
              <th className='px-3 py-2 text-left font-medium'>状态</th>
              <th className='px-3 py-2 text-left font-medium'>类型</th>
              <th className='px-3 py-2 text-left font-medium'>Benchmark</th>
              <th className='px-3 py-2 text-left font-medium'>版本数</th>
              <th className='px-3 py-2 text-left font-medium'>发布人/发布时间</th>
              <th className='px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const meta = STATUS_META[task.status] ?? { label: task.status, variant: 'neutral' as const }
              const expanded = expandedId === task.id
              return (
                <ExpandedRows
                  key={task.id}
                  task={task}
                  meta={meta}
                  expanded={expanded}
                  onToggle={() => setExpandedId(expanded ? null : task.id)}
                  detail={detail}
                  detailLoading={detailLoading}
                  detailError={detailError}
                  hasPermission={hasPermission}
                />
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ExpandedRows({
  task,
  meta,
  expanded,
  onToggle,
  detail,
  detailLoading,
  detailError,
  hasPermission,
}: {
  task: PublishedTaskItem
  meta: { label: string; variant: 'success' | 'neutral' }
  expanded: boolean
  onToggle: () => void
  detail: PublishedTaskDetail | null
  detailLoading: boolean
  detailError: string | null
  hasPermission: (permission: string) => boolean
}) {
  const archived = task.status === 'archived'
  const canExecute = hasPermission('published_task:execute')

  return (
    <>
      <tr
        className={cn(
          'hover:bg-muted/40 border-border/60 border-b transition-colors',
          expanded && 'bg-muted/40'
        )}
      >
        <td className='px-3 py-2'>
          <Button
            variant='ghost'
            size='icon-xs'
            aria-label={expanded ? '收起版本详情' : '展开版本详情'}
            onClick={onToggle}
          >
            <ChevronRight
              aria-hidden='true'
              className={cn('size-4 transition-transform', expanded && 'rotate-90')}
            />
          </Button>
        </td>
        <td className='px-3 py-2'>
          <div className='flex items-center gap-1.5'>
            <Badge className='rounded-md px-1.5'>v{task.version}</Badge>
            {task.is_current && (
              <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                当前
              </Badge>
            )}
          </div>
        </td>
        <td className='max-w-64 px-3 py-2'>
          <span className='block font-medium truncate'>{task.name}</span>
          <span className='text-muted-foreground block truncate'>
            {task.description ?? ''}
          </span>
        </td>
        <td className='px-3 py-2'>
          <StatusBadge label={meta.label} variant={meta.variant} />
        </td>
        <td className='px-3 py-2'>
          <Badge variant='outline' className='rounded-md px-1.5'>
            {getTaskTypeLabel(task.type ?? null)}
          </Badge>
        </td>
        <td className='px-3 py-2'>
          {task.benchmark ? (
            <Tooltip>
              <TooltipTrigger
                render={
                  <span className='inline-flex items-center justify-center'>
                    <Trophy
                      aria-hidden='true'
                      className='text-chart-5 size-4.5 rounded-md bg-chart-5/10 p-0.5'
                    />
                  </span>
                }
              />
              <TooltipContent>参与 Benchmark 排行（实测轨数据源）</TooltipContent>
            </Tooltip>
          ) : (
            <span className='text-muted-foreground'>—</span>
          )}
        </td>
        <td className='px-3 py-2 text-muted-foreground'>
          {(task.version_count ?? 0) > 1 ? `共 ${task.version_count} 个版本` : '—'}
        </td>
        <td className='px-3 py-2'>
          <span className='block whitespace-nowrap'>{task.published_by ?? '—'}</span>
          <span className='text-muted-foreground block whitespace-nowrap text-xs tabular-nums'>
            {formatDateTime(task.published_at)}
          </span>
        </td>
        <td className='px-3 py-2'>
          <div className='flex items-center justify-end gap-1.5'>
            {canExecute && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      size='sm'
                      variant='default'
                      className='h-7'
                      disabled={archived}
                      onClick={() => {}}
                    >
                      执行
                    </Button>
                  }
                />
                <TooltipContent>
                  {archived ? '已归档任务禁止执行，请先创建新版本' : '按当前版本快照创建日常任务'}
                </TooltipContent>
              </Tooltip>
            )}
            <Button size='sm' variant='outline' className='h-7' onClick={onToggle}>
              版本
            </Button>
            {hasPermission('published_task:version') && (
              <Button size='sm' variant='outline' className='h-7' onClick={() => {}}>
                新版本
              </Button>
            )}
            {hasPermission('published_task:read') && (
              <Button size='sm' variant='ghost' className='h-7' onClick={() => {}}>
                重命名
              </Button>
            )}
            {hasPermission('published_task:archive') && (
              <Button
                size='sm'
                variant='ghost'
                className='text-destructive hover:text-destructive h-7'
                onClick={() => {}}
              >
                归档
              </Button>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className='border-border/60 border-b'>
          <td colSpan={9} className='p-0'>
            {detailLoading ? (
              <div className='bg-muted/20 px-4 py-3'>
                <Skeleton className='h-12 w-full' />
                <Skeleton className='mt-3 h-20 w-full' />
                <Skeleton className='mt-3 h-12 w-full' />
              </div>
            ) : detailError ? (
              <div className='bg-muted/20 px-4 py-3 text-sm text-destructive'>
                {detailError}
              </div>
            ) : detail ? (
              <>
                <PublishedExpandRow
                  detail={{
                    ...detail,
                    id: task.id,
                    versions: [
                      task,
                      ...detail.versions.filter((v) => v.id !== task.id),
                    ],
                  }}
                />
                <Separator className='mt-1' />
              </>
            ) : null}
          </td>
        </tr>
      )}
    </>
  )
}
