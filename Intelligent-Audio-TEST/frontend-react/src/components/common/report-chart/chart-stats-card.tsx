/**
 * ChartStatsCard 对位（15_报告域.md §3.7：正态分布统计卡）。
 * 标题「统计信息」+ 设备 Tab + 基础统计前 8 项 +「正方向区间：」+「负方向区间：」。
 * 共享平台件（INT-430 前置条件）；DistributionStats 类型经 application 层再导出（P2-20）。
 */
import { useMemo, useState } from 'react'

import type { DistributionStats } from '@/application/report-view/use-report-charts'

interface ChartStatsCardProps {
  stats: DistributionStats | null
  deviceStats: { label: string; stats: DistributionStats | null }[]
}

const STAT_ROWS: { key: keyof DistributionStats; label: string; format: (v: number) => string }[] = [
  { key: 'count', label: '样本数量', format: (v) => v.toFixed(0) },
  { key: 'mean', label: '平均值 (μ)', format: (v) => v.toFixed(4) },
  { key: 'stdDev', label: '标准差 (σ)', format: (v) => v.toFixed(4) },
  { key: 'min', label: '最小值', format: (v) => v.toFixed(4) },
  { key: 'q1', label: '下四分位数 (Q1)', format: (v) => v.toFixed(4) },
  { key: 'q2', label: '中位数 (Q2)', format: (v) => v.toFixed(4) },
  { key: 'q3', label: '上四分位数 (Q3)', format: (v) => v.toFixed(4) },
  { key: 'max', label: '最大值', format: (v) => v.toFixed(4) },
]

export function ChartStatsCard({ stats, deviceStats }: ChartStatsCardProps) {
  const [activeTab, setActiveTab] = useState('全部')

  const active = useMemo(() => {
    if (activeTab === '全部') return stats
    return deviceStats.find((d) => d.label === activeTab)?.stats ?? null
  }, [activeTab, stats, deviceStats])

  if (!active) return null

  return (
    <div className='rounded-xl border p-3'>
      <div className='flex items-center justify-between gap-2'>
        <p className='text-sm font-medium'>统计信息</p>
        <div className='flex flex-wrap gap-1'>
          {['全部', ...deviceStats.map((d) => d.label)].slice(0, 5).map((tab) => (
            <button
              key={tab}
              type='button'
              className={activeTab === tab ? 'bg-primary text-primary-foreground rounded-md px-2 py-0.5 text-xs' : 'hover:bg-muted text-muted-foreground rounded-md px-2 py-0.5 text-xs'}
              onClick={() => setActiveTab(tab)}
            >
              {tab === '全部' ? '全部' : tab.length > 14 ? `${tab.slice(0, 14)}…` : tab}
            </button>
          ))}
        </div>
      </div>

      <div className='mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4'>
        {STAT_ROWS.map((row) => (
          <div key={row.key} className='flex items-center justify-between text-xs'>
            <span className='text-muted-foreground'>{row.label}</span>
            <span className='font-mono tabular-nums'>
              {row.format(active[row.key] as number)}
            </span>
          </div>
        ))}
      </div>

      <div className='mt-3'>
        <p className='text-muted-foreground text-xs'>正方向区间：</p>
        <div className='mt-1 flex flex-wrap gap-x-4 gap-y-1'>
          {active.positiveRanges.map((r) => (
            <span key={r.label} className='text-xs tabular-nums'>
              {r.label} <span className='font-mono'>{r.percent.toFixed(1)}%</span>
            </span>
          ))}
        </div>
        {active.negativeRanges.some((r) => r.percent > 0) && (
          <>
            <p className='text-muted-foreground mt-2 text-xs'>负方向区间：</p>
            <div className='mt-1 flex flex-wrap gap-x-4 gap-y-1'>
              {active.negativeRanges.map((r) => (
                <span key={r.label} className='text-xs tabular-nums'>
                  {r.label} <span className='font-mono'>{r.percent.toFixed(1)}%</span>
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
