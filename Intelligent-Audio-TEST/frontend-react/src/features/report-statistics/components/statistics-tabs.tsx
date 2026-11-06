/**
 * 统计分析四标签页（15_报告域.md §2.2 §5.2.4：统计维度/统计结果/趋势分析/报表生成）。
 * 统计结果子页签=概览/详细/图表/异常；趋势分析子页签=时间趋势/维度趋势/趋势图表/预测分析。
 * 数据源 application/use-report-statistics（执行统计分析后重查）；导出经 onExport 回调。
 */
import { useState } from 'react'

import { ReportChart } from '@/components/common/report-chart'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import type { ReportStatisticsData } from '@/application/report-statistics/use-report-statistics'
import {
  RESULT_SUB_TABS,
  STATISTIC_TABS,
  TREND_SUB_TABS,
} from '@/features/report-statistics/constants'

import { StatisticsCharts } from './statistics-charts'
import { StatisticsReportForm } from './statistics-report-form'
import { StatisticsTable } from './statistics-table'

interface StatisticsTabsProps {
  data: ReportStatisticsData | undefined
  loading: boolean
  onExport: (scope: string) => void
}

export function StatisticsTabs({ data, loading, onExport }: StatisticsTabsProps) {
  const [resultTab, setResultTab] = useState('overview')
  const [trendTab, setTrendTab] = useState('time')
  const rows = data?.rows ?? []
  const anomalies = data?.anomalyRows ?? []

  return (
    <Tabs defaultValue='dimension'>
      <TabsList className='h-10'>
        {STATISTIC_TABS.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value}>
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>

      <TabsContent value='dimension'>
        <StatisticsTable
          rows={rows}
          anomalies={anomalies}
          isLoading={loading}
          mode='detail'
          onExport={() => onExport('统计维度明细')}
        />
      </TabsContent>

      <TabsContent value='result'>
        <Tabs value={resultTab} onValueChange={setResultTab}>
          <TabsList variant='line' className='mb-3'>
            {RESULT_SUB_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value='overview'>
            <div className='bg-card rounded-2xl border p-4'>
              <p className='text-muted-foreground text-sm leading-6'>
                当前维度共 {rows.length} 个统计项，合计执行用例 {data?.summary.find((s) => s.key === 'cases')?.value ?? 0} 条，
                识别异常 {anomalies.length} 项。详细数据见「详细」页签，图表见「图表」页签。
              </p>
            </div>
          </TabsContent>
          <TabsContent value='detail'>
            <StatisticsTable
              rows={rows}
              anomalies={anomalies}
              isLoading={loading}
              mode='detail'
              onExport={() => onExport('统计结果明细')}
            />
          </TabsContent>
          <TabsContent value='chart'>
            <StatisticsCharts
              scatter={data?.scatter ?? { labels: [], datasets: [] }}
              heatmap={data?.heatmap ?? { labels: [], datasets: [] }}
              loading={loading}
            />
          </TabsContent>
          <TabsContent value='anomaly'>
            <StatisticsTable
              rows={rows}
              anomalies={anomalies}
              isLoading={loading}
              mode='anomaly'
              onExport={() => onExport('异常统计识别')}
            />
          </TabsContent>
        </Tabs>
      </TabsContent>

      <TabsContent value='trend'>
        <Tabs value={trendTab} onValueChange={setTrendTab}>
          <TabsList variant='line' className='mb-3'>
            {TREND_SUB_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value='time'>
            <ReportChart
              title='执行用例数时间趋势'
              subtitle='近 7 天任务执行量变化'
              type='line'
              series={data?.trend ?? { labels: [], datasets: [] }}
              loading={loading}
              enableZoom
            />
          </TabsContent>
          <TabsContent value='dimension'>
            <ReportChart
              title='各维度统计值'
              subtitle='当前统计维度下各分项的对比'
              type='bar'
              series={data?.trend ?? { labels: [], datasets: [] }}
              loading={loading}
              enableZoom={false}
            />
          </TabsContent>
          <TabsContent value='chart'>
            <StatisticsCharts
              scatter={data?.scatter ?? { labels: [], datasets: [] }}
              heatmap={data?.heatmap ?? { labels: [], datasets: [] }}
              loading={loading}
            />
          </TabsContent>
          <TabsContent value='forecast'>
            <div className='bg-card rounded-2xl border p-4'>
              <p className='text-muted-foreground text-sm leading-6'>
                预测分析（趋势预测）暂以统计口径呈现：按当前维度均值外推，预测接入 AI 增强时再启用
                （15_报告域.md §10-4：AI 摘要/异常/趋势预测搁置不引入）。
              </p>
            </div>
          </TabsContent>
        </Tabs>
      </TabsContent>

      <TabsContent value='report'>
        <StatisticsReportForm reportIds={data?.reportIds ?? []} />
      </TabsContent>
    </Tabs>
  )
}
