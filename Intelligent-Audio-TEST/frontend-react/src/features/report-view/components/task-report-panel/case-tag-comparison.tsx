/**
 * 按用例标签对比（15_报告域.md §3.3.6，CaseTagComparison 对位）。
 * 标签筛选器按分类分组展示（分类组头 + 组内标签，标签带 category_id/category_name）；
 * 矩阵行按单标签独立均值；+ 评估维度多选 + 每维度矩阵（表格/图表）。
 */
import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Checkbox } from '@/components/ui/checkbox'
import { useCaseTagComparison } from '@/application/report-view/use-case-tag-comparison'
import { getValidResources } from '@/application/report-view/use-report-summary'
import type { ReportDetailData } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { MetricMatrixTable } from './metric-matrix-table'

export function CaseTagComparison({
  report,
  isExporting,
}: {
  report: ReportDetailData
  isExporting?: boolean
}) {
  const {
    tagGroups,
    matrix,
    filteredTags,
    allMetrics,
    availableMetrics,
    selectedMetrics,
    setSelectedMetrics,
    selectedTags,
    setSelectedTags,
    activeDisplayType,
    setActiveDisplayType,
    effectiveMetrics,
  } = useCaseTagComparison(report)
  const resources = getValidResources(report.summary)
  const [collapsed, setCollapsed] = useState(false)

  const showTags = useMemo(() => filteredTags, [filteredTags])

  return (
    <Collapsible open={!collapsed || isExporting} onOpenChange={setCollapsed} className='space-y-3'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={<Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />}
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>
            按用例标签对比
            <Badge variant='secondary' className='font-mono tabular-nums'>
              {showTags.length}
            </Badge>
          </span>
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-4 transition-transform', collapsed && 'rotate-180')}
          />
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className='space-y-3'>
        {/* 标签筛选卡（按分类分组） */}
        <div className='rounded-xl border p-3'>
          <p className='text-muted-foreground text-xs'>用例标签（按分类分组）：</p>
          <div className='mt-2 space-y-2'>
            {tagGroups.map(([category, tags]) => (
              <div key={category}>
                <p className='text-muted-foreground text-xs font-medium'>{category}</p>
                <div className='mt-1 flex flex-wrap gap-x-4 gap-y-1'>
                  {tags.map((tag) => (
                    <label key={tag.tag_id ?? tag.tag_name} className='flex items-center gap-1.5 text-xs'>
                      <Checkbox
                        checked={selectedTags.includes(tag.tag_name)}
                        onCheckedChange={(checked) => {
                          setSelectedTags((prev) =>
                            checked ? [...prev, tag.tag_name] : prev.filter((t) => t !== tag.tag_name)
                          )
                        }}
                      />
                      {tag.tag_name}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className='mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-2'>
            <span className='text-muted-foreground text-xs'>选择评估维度（可多选）：</span>
            {availableMetrics.map((m) => (
              <label key={m} className='flex items-center gap-1.5 text-xs'>
                <Checkbox
                  checked={selectedMetrics.includes(m)}
                  onCheckedChange={(checked) => {
                    setSelectedMetrics((prev) =>
                      checked ? [...prev, m] : prev.filter((x) => x !== m)
                    )
                  }}
                />
                {m}
              </label>
            ))}
          </div>
          <div className='mt-2 flex items-center justify-end gap-2'>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                setSelectedTags([])
                setSelectedMetrics([])
              }}
            >
              重置
            </Button>
            <Button
              size='sm'
              onClick={() => {
                // 标签/维度过滤为实时生效，此处显式提交并反馈
                toast.success('筛选已应用')
              }}
            >
              应用筛选
            </Button>
          </div>
        </div>

        {showTags.length === 0 ? (
          <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
            暂无可用的用例标签
          </div>
        ) : (
          effectiveMetrics.map((metricName) => {
            const metric = allMetrics.find((m) => m.name === metricName) ?? { name: metricName }
            return (
              <MetricMatrixTable
                key={metricName}
                metric={metric}
                matrix={matrix}
                groups={showTags}
                resources={resources}
                displayType={activeDisplayType}
                onDisplayTypeChange={setActiveDisplayType}
                isExporting={isExporting}
              />
            )
          })
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
