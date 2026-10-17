/**
 * 按用例分组对比（15_报告域.md §3.3.5，CaseCategoryComparison 对位）。
 * 筛选卡（用例名称搜索 / 用例分组多选 / 用例标签多选）+ 评估维度多选 + 每维度矩阵（表格/图表）。
 * 「应用筛选」提交草稿条件生效（draft→applied）；分组名可点击内联重命名 → 防抖 PUT 回写
 * （useReportSummaryEdit，§3.6/验收 #3）。
 */
import { ChevronDown } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { useCaseCategoryComparison } from '@/application/report-view/use-case-category-comparison'
import { getValidResources } from '@/application/report-view/use-report-summary'
import { useReportSummaryEdit } from '@/application/report-view/use-report-summary-edit'
import type { ReportDetailData } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { MetricMatrixTable } from './metric-matrix-table'
import { MultiSelectFilter, SelectedConditionsBar } from './multi-select-filter'

export function CaseCategoryComparison({
  report,
  isExporting,
}: {
  report: ReportDetailData
  isExporting?: boolean
}) {
  const {
    groupKeys,
    allTags,
    matrix,
    filteredGroups,
    allMetrics,
    availableMetrics,
    selectedMetrics,
    setSelectedMetrics,
    selectedGroups,
    setSelectedGroups,
    selectedTags,
    setSelectedTags,
    keyword,
    setKeyword,
    activeDisplayType,
    setActiveDisplayType,
    effectiveMetrics,
    applyFilters,
    resetFilters,
  } = useCaseCategoryComparison(report)
  const resources = getValidResources(report.summary)
  const [collapsed, setCollapsed] = useState(false)
  const { scheduleSaveSummary } = useReportSummaryEdit(report.id)

  // 分组重命名本地映射（old→new；矩阵键保持原名，展示名跟随）
  const [renames, setRenames] = useState<Record<string, string>>({})

  const handleRename = useCallback(
    (group: string, resource: string | undefined, next: string) => {
      // 资源表头 label 编辑（§3.6 commitEditResource → resourceHeaders[].label → 防抖 PUT）
      if (resource !== undefined) {
        scheduleSaveSummary({
          resourceHeaders: report.summary.resource_headers.map((h) =>
            h.key === resource || h.label === resource || h.name === resource
              ? { ...h, label: next }
              : h
          ),
        })
        return
      }
      setRenames((prev) => ({ ...prev, [group]: next }))
      // 持久化：更新源 case_categories 中对应分组名 → 200ms 防抖 → PUT /reports/{id}
      scheduleSaveSummary({
        caseCategories: report.summary.case_categories.map((c) =>
          c.category_name === group ? { ...c, category_name: next } : c
        ),
      })
    },
    [report.summary.case_categories, report.summary.resource_headers, scheduleSaveSummary]
  )

  const showGroups = useMemo(() => filteredGroups, [filteredGroups])

  return (
    <Collapsible open={!collapsed || isExporting} onOpenChange={setCollapsed} className='space-y-3'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={<Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />}
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>
            按用例分组对比
            <Badge variant='secondary' className='font-mono tabular-nums'>
              {showGroups.length}
            </Badge>
          </span>
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-4 transition-transform', collapsed && 'rotate-180')}
          />
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className='space-y-3'>
        {/* 筛选卡（§3.3.5：用例名称 / 用例分组多选 / 评估维度多选；「应用筛选」提交生效） */}
        <div className='rounded-xl border p-3'>
          <div className='flex flex-wrap items-end gap-3'>
            <div className='min-w-40 flex-1'>
              <label className='text-muted-foreground mb-1 block text-xs'>用例名称</label>
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder='搜索用例名称...'
                className='h-8 text-xs'
              />
            </div>
            <div className='flex flex-wrap items-center gap-3'>
              <label className='text-muted-foreground block text-xs'>
                用例分组
                <span className='text-foreground ms-1 font-mono tabular-nums'>{selectedGroups.length}</span>
              </label>
              <label className='text-muted-foreground block text-xs'>
                用例标签
                <span className='text-foreground ms-1 font-mono tabular-nums'>{selectedTags.length}</span>
              </label>
              <label className='text-muted-foreground block text-xs'>
                评估维度
                <span className='text-foreground ms-1 font-mono tabular-nums'>{selectedMetrics.length}</span>
              </label>
            </div>
          </div>
          <div className='mt-2 space-y-1.5 border-t pt-2'>
            {/* 多选组带搜索+分页（§3.3.7/3.3.8；原全铺 checkbox 无界） */}
            <MultiSelectFilter
              label='用例分组'
              options={groupKeys}
              selected={selectedGroups}
              display={(g) => renames[g] ?? g}
              variant='checkbox'
              onToggle={(g) =>
                setSelectedGroups((prev) =>
                  prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]
                )
              }
            />
            <MultiSelectFilter
              label='用例标签'
              options={allTags}
              selected={selectedTags}
              variant='checkbox'
              onToggle={(tag) =>
                setSelectedTags((prev) =>
                  prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag]
                )
              }
            />
            <MultiSelectFilter
              label='评估维度'
              options={availableMetrics}
              selected={selectedMetrics}
              variant='checkbox'
              onToggle={(m) =>
                setSelectedMetrics((prev) =>
                  prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
                )
              }
            />
          </div>
          <SelectedConditionsBar
            conditions={[
              ...selectedGroups.map((g) => ({ key: `group:${g}`, label: `分组·${renames[g] ?? g}` })),
              ...selectedTags.map((t) => ({ key: `tag:${t}`, label: `标签·${t}` })),
              ...selectedMetrics.map((m) => ({ key: `metric:${m}`, label: `维度·${m}` })),
            ]}
            onRemove={(key) => {
              const [kind, ...rest] = key.split(':')
              const value = rest.join(':')
              if (kind === 'group') setSelectedGroups((prev) => prev.filter((x) => x !== value))
              else if (kind === 'tag') setSelectedTags((prev) => prev.filter((x) => x !== value))
              else if (kind === 'metric') setSelectedMetrics((prev) => prev.filter((x) => x !== value))
            }}
          />
          <div className='mt-2 flex items-center justify-end gap-2 border-t pt-2'>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                resetFilters()
                toast.success('筛选已重置')
              }}
            >
              重置
            </Button>
            <Button
              size='sm'
              onClick={() => {
                applyFilters()
                toast.success('筛选已应用')
              }}
            >
              应用筛选
            </Button>
          </div>
        </div>

        {showGroups.length === 0 ? (
          <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
            暂无可用的用例分组
          </div>
        ) : (
          effectiveMetrics.map((metricName) => {
            const metric = allMetrics.find((m) => m.name === metricName) ?? { name: metricName }
            return (
              <MetricMatrixTable
                key={metricName}
                metric={metric}
                matrix={matrix}
                groups={showGroups}
                resources={resources}
                displayType={activeDisplayType}
                onDisplayTypeChange={setActiveDisplayType}
                isExporting={isExporting}
                groupLabels={renames}
                onRename={handleRename}
              />
            )
          })
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
