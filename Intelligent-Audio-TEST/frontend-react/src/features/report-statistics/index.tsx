/**
 * /report-statistics 报告统计分析页（15_报告域.md §2.2，INT-381 返修补全；INT-500 路由定稿）。
 * 入口=报告中心工具栏「更多操作 ⋯ → 统计分析」；report:read 守卫。
 * 功能：报告数量/测试用例执行/评估指标/设备性能统计 + 时间/任务类型/设备类型/评估维度四维统计
 * + 统计表格/图表（散点·热力）/统计分析报告/异常统计识别 + 四标签页 + 统计结果导出（§4.3 复用）。
 */
import { FileDown } from 'lucide-react'
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { StatBadge } from '@/features/tasks/components/ui/stat-badge'
import { useReportStatistics, type StatisticsTimeRange } from '@/application/report-statistics/use-report-statistics'
import { useStatisticsExport } from '@/application/report-statistics/use-statistics-export'
import { STATISTIC_SUMMARY_CARDS, type StatisticDimension } from '@/features/report-statistics/constants'

import { StatisticsDimensionSelect } from './components/statistics-dimension-select'
import { StatisticsTabs } from './components/statistics-tabs'

export function ReportStatisticsPage() {
  const [dimension, setDimension] = useState<StatisticDimension>('time')
  const [range, setRange] = useState<StatisticsTimeRange>({})
  const [runSeq, setRunSeq] = useState(0)
  const { exportStatistics } = useStatisticsExport()

  // 执行统计分析：queryKey 注入 runSeq，点击「执行统计分析」即重查（§4.4 流程）
  const statsQuery = useReportStatistics(dimension, range, runSeq)
  const data = statsQuery.data
  const summary = data?.summary ?? []

  const handleRun = useCallback(() => {
    setRunSeq((seq) => seq + 1)
    toast.success('统计完成')
  }, [])

  const handleExport = useCallback(
    (scope: string) => {
      exportStatistics('excel', `${scope}（${dimension}）`)
    },
    [dimension, exportStatistics]
  )

  return (
    <SectionPageLayout fixedContent>
      <SectionPageLayout.Title>
        <span className='inline-flex items-center gap-2'>
          报告统计分析
          <Badge variant='outline' className='font-mono tabular-nums'>
            维度：{dimension}
          </Badge>
        </span>
      </SectionPageLayout.Title>

      <SectionPageLayout.Actions>
        <Button variant='outline' size='sm' onClick={() => handleExport('统计结果')}>
          <FileDown data-icon='inline-start' />
          导出统计结果
        </Button>
      </SectionPageLayout.Actions>

      <SectionPageLayout.Content>
        <div className='flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-4'>
          <StatisticsDimensionSelect
            dimension={dimension}
            onDimensionChange={setDimension}
            range={range}
            onRangeChange={setRange}
            onRun={handleRun}
          />

          {/* 统计卡（报告数量/用例执行/评估指标/设备性能） */}
          <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
            {STATISTIC_SUMMARY_CARDS.map((card) => {
              const item = summary.find((s) => s.key === card.key)
              return (
                <div
                  key={card.key}
                  className='bg-card flex flex-col gap-1 rounded-2xl border p-4 shadow-xs'
                >
                  <span className='text-muted-foreground text-xs font-medium'>{card.label}</span>
                  <span className='font-mono text-2xl font-semibold tabular-nums'>
                    {item?.value ?? 0}
                  </span>
                  <span className='text-muted-foreground text-xs leading-5'>{item?.hint}</span>
                </div>
              )
            })}
          </div>

          <StatBadge
            label='统计维度'
            value={dimension === 'time' ? '时间' : dimension === 'task_type' ? '任务类型' : dimension === 'device_type' ? '设备类型' : '评估维度'}
            colorClass='bg-info'
          />

          <StatisticsTabs
            data={data}
            loading={statsQuery.isLoading}
            onExport={handleExport}
          />
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
