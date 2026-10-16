/**
 * 具体用例（15_报告域.md §3.3.7，SpecificCaseComparison 对位）。
 * 筛选卡（名称搜索/分组/标签/维度/排序）+ 已固定用例区 + 用例列表（状态点 + 名称 + 分组徽标
 * + CaseIdBadge + 标签 + 下载日志 + 展开）+ 展开详情 = TestCaseReportDetail 七块（§3.5）。
 */
import { ArrowDownWideNarrow, ArrowUpNarrowWide, ChevronDown, Download, Pin, PinOff } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { useReportCases } from '@/application/report-view/use-report-cases'
import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { CaseReportDetail } from '../case-report-detail'
import { CaseDetailDialog } from '../modals/case-detail-dialog'
import { LogDownloadProgressDialog } from '../modals/log-download-progress-dialog'

export function SpecificCaseComparison({
  report,
  isExporting,
}: {
  report: ReportDetailData
  isExporting?: boolean
}) {
  const fallbackCases = report.summary.cases ?? []
  const {
    filters,
    setFilters,
    applyFilters,
    resetFilters,
    items,
    isLoading,
    isError,
    refetch,
    total,
    page,
    setPage,
    pages,
    pinnedIds,
    pinnedCases,
    togglePin,
    expandedIds,
    toggleExpand,
    downloadLogs,
  } = useReportCases(report.id, fallbackCases)

  // 筛选卡可选项（分组/标签/评估维度；标签合并自用例 + summary 标签池）
  const availableGroups = useMemo(
    () => report.summary.case_categories.map((c) => c.category_name).filter(Boolean),
    [report.summary.case_categories]
  )
  const availableTags = useMemo(() => {
    const set = new Set<string>()
    for (const c of fallbackCases) for (const t of c.tags) set.add(t)
    for (const tag of [...(report.summary.all_tags ?? []), ...report.summary.all_case_tags]) {
      if (tag.tag_name) set.add(tag.tag_name)
    }
    return [...set]
  }, [fallbackCases, report.summary.all_tags, report.summary.all_case_tags])
  const availableMetrics = useMemo(
    () => report.summary.all_metrics.map((m) => m.name),
    [report.summary.all_metrics]
  )

  const [collapsed, setCollapsed] = useState(false)
  const [detailCase, setDetailCase] = useState<ReportCaseItem>()
  const [downloadingId, setDownloadingId] = useState<string>()
  const [downloadTarget, setDownloadTarget] = useState<ReportCaseItem>()
  const [downloadSize, setDownloadSize] = useState(0)

  const handleDownload = async (caseId: string) => {
    setDownloadingId(caseId)
    try {
      const { size } = await downloadLogs(caseId)
      const target =
        items.find((c) => c.id === caseId) ??
        fallbackCases.find((c) => c.id === caseId)
      setDownloadSize(size)
      setDownloadTarget(target)
    } finally {
      setDownloadingId(undefined)
    }
  }

  return (
    <Collapsible open={!collapsed || isExporting} onOpenChange={setCollapsed} className='space-y-3'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={<Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />}
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>
            具体用例对比
            <Badge variant='secondary' className='font-mono tabular-nums'>
              共 {total} 个用例
            </Badge>
          </span>
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-4 transition-transform', collapsed && 'rotate-180')}
          />
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className='space-y-3'>
        {/* 筛选卡（§3.3.7：名称/分组多选/标签多选/评估维度多选/排序[按评估维度含资源+维度+升降序]） */}
        <div className='rounded-xl border p-3'>
          <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
            <div>
              <label className='text-muted-foreground mb-1 block text-xs'>用例名称</label>
              <Input
                value={filters.keyword ?? ''}
                onChange={(e) => setFilters({ ...filters, keyword: e.target.value })}
                placeholder='输入用例ID或名称关键词'
                className='h-8 text-xs'
              />
            </div>
            <div>
              <label className='text-muted-foreground mb-1 block text-xs'>排序方式</label>
              <div className='flex items-center gap-1.5'>
                <Select
                  value={filters.sortBy ?? 'name'}
                  onValueChange={(v) =>
                    setFilters({ ...filters, sortBy: v as typeof filters.sortBy })
                  }
                >
                  <SelectTrigger className='h-8 flex-1 text-xs'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='name'>按名称</SelectItem>
                    <SelectItem value='category'>按分组</SelectItem>
                    <SelectItem value='createdat'>按创建时间</SelectItem>
                    <SelectItem value='metric'>按评估维度</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant='outline'
                  size='sm'
                  className='h-8 px-2'
                  aria-label={filters.sortOrder === 'desc' ? '降序' : '升序'}
                  title={filters.sortOrder === 'desc' ? '降序' : '升序'}
                  onClick={() =>
                    setFilters({
                      ...filters,
                      sortOrder: filters.sortOrder === 'desc' ? 'asc' : 'desc',
                    })
                  }
                >
                  {filters.sortOrder === 'desc' ? (
                    <ArrowDownWideNarrow aria-hidden='true' className='size-3.5' />
                  ) : (
                    <ArrowUpNarrowWide aria-hidden='true' className='size-3.5' />
                  )}
                </Button>
              </div>
            </div>
            {filters.sortBy === 'metric' && (
              <div className='grid grid-cols-2 gap-1.5'>
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>资源</label>
                  <Select
                    value={filters.sortResource ?? 'all'}
                    onValueChange={(v) =>
                      setFilters({ ...filters, sortResource: v === 'all' || v === null ? undefined : v })
                    }
                  >
                    <SelectTrigger className='h-8 text-xs'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='all'>全部资源(平均)</SelectItem>
                      {report.summary.resources.map((r) => (
                        <SelectItem key={r} value={r}>{r}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>评估维度</label>
                  <Select
                    value={filters.sortMetric ?? availableMetrics[0] ?? 'all'}
                    onValueChange={(v) =>
                      setFilters({ ...filters, sortMetric: v === 'all' || v === null ? undefined : v })
                    }
                  >
                    <SelectTrigger className='h-8 text-xs'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableMetrics.map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>

          <div className='mt-2 space-y-1.5 border-t pt-2'>
            <div className='flex flex-wrap items-center gap-1.5'>
              <span className='text-muted-foreground w-16 shrink-0 text-xs'>用例分组</span>
              {availableGroups.map((g) => {
                const active = filters.categories?.includes(g) ?? false
                return (
                  <button
                    key={g}
                    type='button'
                    aria-pressed={active}
                    className={cn(
                      'rounded-md px-2 py-0.5 text-xs transition-colors',
                      active
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted text-muted-foreground'
                    )}
                    onClick={() =>
                      setFilters({
                        ...filters,
                        categories: active
                          ? (filters.categories ?? []).filter((x) => x !== g)
                          : [...(filters.categories ?? []), g],
                      })
                    }
                  >
                    {g}
                  </button>
                )
              })}
            </div>
            <div className='flex flex-wrap items-center gap-1.5'>
              <span className='text-muted-foreground w-16 shrink-0 text-xs'>用例标签</span>
              {availableTags.map((t) => {
                const active = filters.tags?.includes(t) ?? false
                return (
                  <button
                    key={t}
                    type='button'
                    aria-pressed={active}
                    className={cn(
                      'rounded-md px-2 py-0.5 text-xs transition-colors',
                      active
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted text-muted-foreground'
                    )}
                    onClick={() =>
                      setFilters({
                        ...filters,
                        tags: active
                          ? (filters.tags ?? []).filter((x) => x !== t)
                          : [...(filters.tags ?? []), t],
                      })
                    }
                  >
                    {t}
                  </button>
                )
              })}
            </div>
            <div className='flex flex-wrap items-center gap-1.5'>
              <span className='text-muted-foreground w-16 shrink-0 text-xs'>评估维度</span>
              {availableMetrics.map((m) => {
                const active = filters.metrics?.includes(m) ?? false
                return (
                  <button
                    key={m}
                    type='button'
                    aria-pressed={active}
                    className={cn(
                      'rounded-md px-2 py-0.5 text-xs transition-colors',
                      active
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted text-muted-foreground'
                    )}
                    onClick={() =>
                      setFilters({
                        ...filters,
                        metrics: active
                          ? (filters.metrics ?? []).filter((x) => x !== m)
                          : [...(filters.metrics ?? []), m],
                      })
                    }
                  >
                    {m}
                  </button>
                )
              })}
            </div>
          </div>

          <div className='mt-2 flex items-center justify-end gap-2 border-t pt-2'>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                resetFilters()
                void refetch()
              }}
            >
              重置
            </Button>
            <Button
              size='sm'
              onClick={() => {
                applyFilters(filters)
                void refetch()
              }}
            >
              应用筛选
            </Button>
          </div>
        </div>

        {/* 已固定用例 */}
        {pinnedCases.length > 0 && (
          <div className='rounded-xl border p-3'>
            <p className='text-muted-foreground text-xs font-medium'>已固定用例</p>
            <div className='mt-2 flex flex-wrap gap-2'>
              {pinnedCases.map((c) => (
                <div key={c.id} className='bg-muted/40 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs'>
                  <span className='font-medium'>{c.name}</span>
                  <Button
                    variant='ghost'
                    size='sm'
                    className='text-muted-foreground h-5 px-1'
                    aria-label='取消固定'
                    onClick={() => togglePin(c.id)}
                  >
                    <PinOff aria-hidden='true' className='size-3' />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 用例列表 */}
        <div className='space-y-2'>
          {isLoading && items.length === 0 ? (
            <p className='text-muted-foreground p-4 text-center text-sm'>正在加载用例数据...</p>
          ) : isError && items.length === 0 ? (
            <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
              加载失败
            </div>
          ) : items.length === 0 ? (
            <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
              暂无数据
            </div>
          ) : (
            items.map((c) => {
              const status = c.overall_status ?? overallStatusOf(c)
              const expanded = expandedIds.includes(c.id)
              const pinned = pinnedIds.includes(c.id)
              return (
                <div key={c.id} className='rounded-xl border'>
                  <div className='flex items-center gap-2 px-3 py-2.5'>
                    <StatusDot status={status} />
                    <div className='min-w-0 flex-1'>
                      <div className='flex items-center gap-2'>
                        <span className='truncate text-sm font-medium'>{c.name}</span>
                        <Badge variant='outline' className='text-xs'>
                          {c.category ?? '未分类'}
                        </Badge>
                        <span className='text-muted-foreground font-mono text-xs'>{c.id}</span>
                      </div>
                      <div className='mt-1 flex flex-wrap gap-1'>
                        {c.tags.map((tag) => (
                          <Badge key={tag} variant='secondary' className='text-xs'>
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-7 gap-1 px-2 text-xs'
                      onClick={() => void handleDownload(c.id)}
                      disabled={downloadingId === c.id}
                    >
                      <Download aria-hidden='true' className='size-3.5' />
                      下载日志
                    </Button>
                    <Button
                      variant='ghost'
                      size='sm'
                      className='text-muted-foreground h-7 px-1.5'
                      aria-pressed={pinned}
                      onClick={() => togglePin(c.id)}
                    >
                      <Pin aria-hidden='true' className={cn('size-3.5', pinned && 'text-primary fill-primary/20')} />
                    </Button>
                    <Button variant='ghost' size='sm' className='h-7 px-1.5' onClick={() => setDetailCase(c)}>
                      详情
                    </Button>
                    <Button variant='ghost' size='sm' className='h-7 px-1.5' onClick={() => toggleExpand(c.id)}>
                      <ChevronDown
                        aria-hidden='true'
                        className={cn('size-4 transition-transform', expanded && 'rotate-180')}
                      />
                    </Button>
                  </div>
                  {expanded && (
                    <div className='border-t p-3'>
                      <CaseReportDetail caseItem={c} report={report} />
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* 分页 */}
        {pages > 1 && !isExporting && (
          <div className='flex items-center justify-between text-xs'>
            <span className='text-muted-foreground'>第 {page} / {pages} 页</span>
            <div className='flex items-center gap-1'>
              <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page <= 1} onClick={() => setPage(page - 1)}>
                上一页
              </Button>
              <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page >= pages} onClick={() => setPage(page + 1)}>
                下一页
              </Button>
            </div>
          </div>
        )}
      </CollapsibleContent>

      <LogDownloadProgressDialog
        open={downloadTarget !== undefined}
        onOpenChange={(open) => {
          if (!open) setDownloadTarget(undefined)
        }}
        caseName={downloadTarget?.name ?? ''}
        totalSize={downloadSize}
        onComplete={() => {
          setDownloadTarget(undefined)
          toast.success('日志下载完成')
        }}
      />
      <CaseDetailDialog
        open={detailCase !== undefined}
        onOpenChange={(open) => {
          if (!open) setDetailCase(undefined)
        }}
        caseItem={detailCase}
        report={report}
      />
    </Collapsible>
  )
}

function overallStatusOf(c: ReportCaseItem): 'pass' | 'fail' | 'warning' | 'skip' | 'unknown' {
  const statuses = c.results.map((r) => r.status ?? '')
  if (statuses.some((s) => s === 'failed')) return 'fail'
  if (statuses.some((s) => s === 'skipped')) return 'skip'
  if (statuses.some((s) => s === 'warning')) return 'warning'
  return statuses.length > 0 ? 'pass' : 'unknown'
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === 'pass' || status === 'completed'
      ? 'bg-success'
      : status === 'fail' || status === 'failed'
        ? 'bg-destructive'
        : status === 'warning'
          ? 'bg-warning'
          : status === 'skip'
            ? 'bg-muted'
            : 'bg-muted-foreground/40'
  return <span aria-hidden='true' className={cn('size-2 shrink-0 rounded-full', color)} />
}
