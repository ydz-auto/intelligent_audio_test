/**
 * 按用例分组对比（15_报告域.md §3.3.5，CaseCategoryComparison 对位）。
 * 筛选卡（用例名称搜索 / 用例分组多选 / 用例标签多选）+ 评估维度多选 + 每维度矩阵（表格/图表）。
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
import { Input } from '@/components/ui/input'
import { useCaseCategoryComparison } from '@/application/report-view/use-case-category-comparison'
import { getValidResources } from '@/application/report-view/use-report-summary'
import type { ReportDetailData } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { MetricMatrixTable } from './metric-matrix-table'

export function CaseCategoryComparison({
  report,
  isExporting,
}: {
  report: ReportDetailData
  isExporting?: boolean
}) {
  const {
    groupKeys,
    matrix,
    filteredGroups,
    allMetrics,
    availableMetrics,
    selectedMetrics,
    setSelectedMetrics,
    selectedGroups,
    setSelectedGroups,
    keyword,
    setKeyword,
    activeDisplayType,
    setActiveDisplayType,
    effectiveMetrics,
  } = useCaseCategoryComparison(report)
  const resources = getValidResources(report.summary)
  const [collapsed, setCollapsed] = useState(false)

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
        {/* 筛选卡（§3.3.5：用例名称 / 用例分组多选 / 评估维度多选；重置与应用筛选已接线） */}
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
                评估维度
                <span className='text-foreground ms-1 font-mono tabular-nums'>{selectedMetrics.length}</span>
              </label>
            </div>
          </div>
          <div className='mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-2'>
            <span className='text-muted-foreground text-xs'>选择用例分组（可多选）：</span>
            {groupKeys.map((g) => (
              <label key={g} className='flex items-center gap-1.5 text-xs'>
                <Checkbox
                  checked={selectedGroups.includes(g)}
                  onCheckedChange={(checked) => {
                    setSelectedGroups((prev) =>
                      checked ? [...prev, g] : prev.filter((x) => x !== g)
                    )
                  }}
                />
                {g}
              </label>
            ))}
          </div>
          <div className='mt-2 flex flex-wrap items-center gap-x-4 gap-y-1'>
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
          <div className='mt-2 flex items-center justify-end gap-2 border-t pt-2'>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                setKeyword('')
                setSelectedGroups([])
                setSelectedMetrics([])
              }}
            >
              重置
            </Button>
            <Button
              size='sm'
              onClick={() => {
                // 分组/维度/关键字过滤为实时生效，此处显式提交并反馈
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
              />
            )
          })
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
