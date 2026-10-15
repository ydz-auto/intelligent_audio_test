/**
 * 设备与 API 统计（规范 §4.4）：Collapsible 默认展开，标题带计数 Badge「设备 {d} · API {a}」。
 * 数量 ≤12 走统计卡栅格（名称 + 型号/厂商 + 状态徽标 + 总用例/完成/失败/成功率 + metrics 网格），
 * 数量多时降级静态表（本卡 mock ≤12，卡栅格为主）。
 */
import { ChevronDown, Cpu, Globe } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type {
  ReportApiStat,
  ReportDetailData,
  ReportDeviceStat,
} from '@/domain/models/report'
import { cn } from '@/lib/utils'

function successVariant(rate: number) {
  if (rate >= 95) return 'success' as const
  if (rate >= 90) return 'warning' as const
  return 'danger' as const
}

function DeviceApiCard({
  name,
  subtitle,
  status,
  totalCases,
  completedCases,
  failedCases,
  successRate,
  metrics,
}: {
  name: string
  subtitle?: string
  status?: string
  totalCases: number
  completedCases: number
  failedCases: number
  successRate: number
  metrics?: Record<string, unknown>
}) {
  return (
    <div className='bg-background rounded-lg border p-3'>
      <div className='flex items-start justify-between gap-2'>
        <div className='min-w-0'>
          <div className='truncate text-sm font-medium'>{name}</div>
          {subtitle && (
            <div className='text-muted-foreground truncate text-xs'>{subtitle}</div>
          )}
        </div>
        <StatusBadge
          label={status === 'online' || status === 'active' ? '在线' : status === 'offline' ? '离线' : '离线'}
          variant={status === 'online' || status === 'active' ? 'success' : 'neutral'}
          size='sm'
        />
      </div>
      <div className='text-muted-foreground mt-3 grid grid-cols-3 gap-2 border-b pb-2 text-xs'>
        <div>
          总用例
          <span className='text-foreground font-mono ml-1 tabular-nums'>{totalCases}</span>
        </div>
        <div>
          完成
          <span className='text-success font-mono ml-1 tabular-nums'>{completedCases}</span>
        </div>
        <div>
          失败
          <span className='text-destructive font-mono ml-1 tabular-nums'>{failedCases}</span>
        </div>
      </div>
      <div className='mt-2 flex items-center justify-between text-xs'>
        <span className='text-muted-foreground'>成功率</span>
        <StatusBadge
          label={`${successRate.toFixed(1)}%`}
          variant={successVariant(successRate)}
          size='sm'
        />
      </div>
      {metrics && Object.keys(metrics).length > 0 && (
        <div className='mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t pt-2 text-xs'>
          {Object.entries(metrics).slice(0, 4).map(([key, value]) => (
            <div key={key} className='flex items-center justify-between gap-1'>
              <span className='text-muted-foreground truncate'>{key}</span>
              <span className='font-mono tabular-nums'>
                {typeof value === 'number' ? value.toFixed(1) : String(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DeviceStatsGrid({ report }: { report: ReportDetailData }) {
  const devices: ReportDeviceStat[] = report.summary.device_stats
  const apis: ReportApiStat[] = report.summary.api_stats

  return (
    <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3'>
      {devices.map((device) => (
        <DeviceApiCard
          key={`device-${device.id}`}
          name={device.name}
          subtitle={[device.model, device.type].filter(Boolean).join(' · ')}
          status={device.status}
          totalCases={device.total_cases}
          completedCases={device.completed_cases}
          failedCases={device.failed_cases}
          successRate={device.success_rate}
          metrics={device.metrics}
        />
      ))}
      {apis.map((api) => (
        <DeviceApiCard
          key={`api-${api.id}`}
          name={api.name}
          subtitle={api.status === 'active' ? '在线 API' : '离线 API'}
          status={api.status}
          totalCases={api.total_cases}
          completedCases={api.completed_cases}
          failedCases={api.failed_cases}
          successRate={api.success_rate}
          metrics={api.metrics}
        />
      ))}
    </div>
  )
}

export function ReportResourceStats({ report }: { report: ReportDetailData }) {
  const [open, setOpen] = useState(true)
  const deviceCount = report.summary.device_stats.length
  const apiCount = report.summary.api_stats.length
  const empty = deviceCount === 0 && apiCount === 0

  return (
    <Collapsible open={open} onOpenChange={setOpen} className='space-y-3'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={<Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />}
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>
            <Cpu className='text-muted-foreground size-4' />
            设备与API统计
            <Badge variant='secondary' className='font-mono tabular-nums'>
              设备 {deviceCount} · API {apiCount}
            </Badge>
          </span>
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-4 transition-transform', open && 'rotate-180')}
          />
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent>
        {empty ? (
          <div className='text-muted-foreground flex h-24 items-center justify-center rounded-lg border text-xs'>
            <Globe className='mr-1.5 size-4' aria-hidden='true' />
            暂无设备与 API 数据
          </div>
        ) : (
          <DeviceStatsGrid report={report} />
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
