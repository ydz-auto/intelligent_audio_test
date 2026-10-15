/**
 * 具体用例（规范 §4.7，SpecificCaseComparison 重设计）：
 * 筛选卡（名称搜索 + 分组/标签/评估维度 chips + 排序 Select + 重置/应用筛选）+
 * 用例列表（状态点 + 名称 + 分组 Badge + CaseIdBadge + 标签 + 展开详情 + 下载日志）+
 * 分页。数据 POST /reports/{id}/cases/search（全参 mock）。
 */
import {
  ChevronDown,
  Download,
  Filter,
  RotateCcw,
  Search,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { StatusBadge, dotColorMap } from '@/features/dashboard/components/ui/status-badge'
import { useReportCases } from '@/application/report-view/use-report-cases'
import type { ReportDetailData, ReportSearchCasesRequest } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { CASE_STATUS_META } from '@/features/reports/constants'
import { ReportsPagination } from '@/features/reports/components/reports-pagination'
import { ReportCaseDetail } from './report-case-detail'

function ChipGroup({
  options,
  selected,
  onToggle,
  label,
}: {
  options: { value: string; label: string }[]
  selected: string[]
  onToggle: (value: string) => void
  label: string
}) {
  if (options.length === 0) return null
  return (
    <div className='space-y-1.5'>
      <span className='text-muted-foreground text-xs'>{label}</span>
      <div className='flex flex-wrap gap-1.5'>
        {options.map((option) => {
          const active = selected.includes(option.value)
          return (
            <Button
              key={option.value}
              variant={active ? 'default' : 'outline'}
              size='sm'
              aria-pressed={active}
              className='h-7 rounded-lg px-2.5 text-xs'
              onClick={() => onToggle(option.value)}
            >
              {option.label}
            </Button>
          )
        })}
      </div>
    </div>
  )
}

export function ReportCaseList({ report }: { report: ReportDetailData }) {
  const [keyword, setKeyword] = useState('')
  const [appliedKeyword, setAppliedKeyword] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [tags, setTags] = useState<string[]>([])
  const [metrics, setMetrics] = useState<string[]>([])
  const [sortBy, setSortBy] = useState<'name' | 'category' | 'createdat' | 'metric'>('name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const query = useMemo<ReportSearchCasesRequest>(
    () => ({
      keyword: appliedKeyword || undefined,
      categories: categories.length ? categories : undefined,
      tags: tags.length ? tags : undefined,
      metrics: metrics.length ? metrics : undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      page,
      per_page: pageSize,
    }),
    [appliedKeyword, categories, tags, metrics, sortBy, sortOrder, page, pageSize]
  )

  const casesQuery = useReportCases(report.id, query)
  const cases = casesQuery.data?.items ?? []
  const total = casesQuery.data?.total ?? 0

  const categoryOptions = report.summary.case_categories.map((c) => ({
    value: c.category_id ?? c.category_name,
    label: c.category_name,
  }))
  const tagOptions = report.summary.all_case_tags.map((t) => ({
    value: t.tag_id ?? t.tag_name,
    label: t.tag_name,
  }))
  const metricOptions = report.summary.all_metrics.map((m) => ({ value: m, label: m }))

  const toggle = (list: string[], value: string, setter: (v: string[]) => void) =>
    setter(list.includes(value) ? list.filter((x) => x !== value) : [...list, value])

  const handleApply = () => {
    setAppliedKeyword(keyword.trim())
    setPage(1)
  }
  const handleReset = () => {
    setKeyword('')
    setAppliedKeyword('')
    setCategories([])
    setTags([])
    setMetrics([])
    setSortBy('name')
    setSortOrder('asc')
    setPage(1)
  }
  const handleDownloadLog = (caseId: string) => {
    // TODO(API 接线): GET /reports/{id}/cases/{caseId}/logs/download（logs.zip Blob + 进度 Dialog）
    toast.success(`用例 ${caseId} 日志开始下载`)
  }

  return (
    <div className='space-y-3'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex items-center gap-2'>
          <Filter className='text-muted-foreground size-4' aria-hidden='true' />
          <h3 className='text-sm font-semibold'>具体用例</h3>
          <Badge variant='secondary' className='font-mono tabular-nums'>
            共 {total} 个用例
          </Badge>
        </div>
        <span className='text-muted-foreground text-xs'>
          POST /reports/{report.id}/cases/search
        </span>
      </div>

      <div className='bg-card rounded-xl border p-4'>
        <div className='grid gap-3 lg:grid-cols-[1fr_auto]'>
          <div className='relative'>
            <Search className='text-muted-foreground/60 pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2' />
            <Input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') handleApply()
              }}
              placeholder='输入用例ID或名称关键词'
              className='pl-9'
            />
          </div>
          <div className='flex items-center gap-2'>
            <Select value={sortBy} onValueChange={(v) => setSortBy(v as typeof sortBy)}>
              <SelectTrigger size='sm' aria-label='排序方式'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent align='end'>
                <SelectItem value='name'>按名称</SelectItem>
                <SelectItem value='category'>按分组</SelectItem>
                <SelectItem value='createdat'>按创建时间</SelectItem>
                <SelectItem value='metric'>按评估维度</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={sortOrder}
              onValueChange={(v) => setSortOrder(v as 'asc' | 'desc')}
            >
              <SelectTrigger size='sm' aria-label='排序方向'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent align='end'>
                <SelectItem value='asc'>升序</SelectItem>
                <SelectItem value='desc'>降序</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className='mt-3 space-y-3 border-t pt-3'>
          <ChipGroup
            label='用例分组'
            options={categoryOptions}
            selected={categories}
            onToggle={(v) => toggle(categories, v, setCategories)}
          />
          <ChipGroup
            label='标签筛选'
            options={tagOptions}
            selected={tags}
            onToggle={(v) => toggle(tags, v, setTags)}
          />
          <ChipGroup
            label='评估维度筛选'
            options={metricOptions}
            selected={metrics}
            onToggle={(v) => toggle(metrics, v, setMetrics)}
          />
        </div>

        <div className='mt-3 flex items-center justify-end gap-2 border-t pt-3'>
          <Button variant='outline' size='sm' onClick={handleReset}>
            <RotateCcw data-icon='inline-start' />
            重置
          </Button>
          <Button size='sm' onClick={handleApply}>
            应用筛选
          </Button>
        </div>
      </div>

      {casesQuery.isLoading && cases.length === 0 ? (
        <div className='text-muted-foreground flex h-32 items-center justify-center text-sm'>
          正在加载用例数据...
        </div>
      ) : cases.length === 0 ? (
        <div className='text-muted-foreground flex h-32 flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-sm'>
          <span>暂无用例数据</span>
          <span className='text-xs'>该报告不含用例，或调整筛选条件试试</span>
        </div>
      ) : (
        <ul className='space-y-2'>
          {cases.map((caseItem) => {
            const statusMeta = CASE_STATUS_META[caseItem.overall_status] ?? CASE_STATUS_META.unknown
            return (
              <li key={caseItem.id} className='bg-card overflow-hidden rounded-lg border'>
                <Collapsible className='w-full'>
                  <div className='flex items-center gap-2 px-3 py-2'>
                    <span
                      aria-hidden='true'
                      className={cn('size-1.5 shrink-0 rounded-full', dotColorMap[statusMeta.variant])}
                    />
                    <StatusBadge label={statusMeta.label} variant={statusMeta.variant} size='sm' />
                    <span className='min-w-0 flex-1 truncate text-sm font-medium'>
                      {caseItem.name}
                    </span>
                    {caseItem.category && (
                      <Badge variant='secondary' className='shrink-0'>
                        {caseItem.category}
                      </Badge>
                    )}
                    <Badge variant='outline' className='font-mono shrink-0'>
                      {caseItem.id}
                    </Badge>
                    {caseItem.tags.slice(0, 3).map((tag) => (
                      <Badge key={tag} variant='ghost' className='hidden shrink-0 sm:inline-flex'>
                        {tag}
                      </Badge>
                    ))}
                    <Button
                      variant='ghost'
                      size='icon-sm'
                      className='shrink-0'
                      aria-label={`下载 ${caseItem.name} 日志`}
                      onClick={() => handleDownloadLog(caseItem.id)}
                    >
                      <Download className='size-3.5' />
                    </Button>
                    <CollapsibleTrigger
                      render={
                        <Button variant='ghost' size='icon-sm' aria-label='展开用例详情' />
                      }
                    >
                      <ChevronDown className='size-4' />
                    </CollapsibleTrigger>
                  </div>
                  <CollapsibleContent className='px-3 pb-3'>
                    <ReportCaseDetail caseItem={caseItem} />
                  </CollapsibleContent>
                </Collapsible>
              </li>
            )
          })}
        </ul>
      )}

      <ReportsPagination
        page={page}
        pageSize={pageSize}
        total={total}
        pages={casesQuery.data?.pages ?? 1}
        entityLabel='用例'
        onPageChange={setPage}
        onPageSizeChange={(next) => {
          setPageSize(next)
          setPage(1)
        }}
      />
    </div>
  )
}
