/**
 * 选择要对比的设备和 API（15_报告域.md §3.4，unified-selector 对位）。
 * comparisonDevices 列表项（设备/API icon + 名称 + 类型徽标 + 选中 ✓），点击切换 toggleDevice。
 * 源 summary.devices + summary.apis（去重）。
 */
import { Check, Cpu, Globe } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { ReportDetailData } from '@/domain/models/report'
import { cn } from '@/lib/utils'

interface DeviceApiSelectorProps {
  report: ReportDetailData
  selectedIds: Set<number>
  onToggle: (id: number) => void
}

export function DeviceApiSelector({
  report,
  selectedIds,
  onToggle,
}: DeviceApiSelectorProps) {
  const devices = report.summary.devices ?? []
  const apis = report.summary.apis ?? []
  const empty = devices.length === 0 && apis.length === 0

  return (
    <div className='rounded-2xl border p-4'>
      <p className='text-sm font-semibold'>选择要对比的设备和API</p>
      {empty ? (
        <div className='text-muted-foreground mt-3 flex h-20 items-center justify-center rounded-lg border text-xs'>
          <Globe aria-hidden='true' className='mr-1.5 size-4' />
          暂无设备与API
        </div>
      ) : (
      <div className='mt-3 grid gap-1.5 sm:grid-cols-2'>
        {devices.map((device) => (
          <SelectorRow
            key={`d-${device.id}`}
            icon={<Cpu aria-hidden='true' className='size-4' />}
            name={device.name}
            kind='设备'
            selected={selectedIds.has(device.id)}
            onToggle={() => onToggle(device.id)}
          />
        ))}
        {apis.map((api) => (
          <SelectorRow
            key={`a-${api.id}`}
            icon={<Globe aria-hidden='true' className='size-4' />}
            name={api.name}
            kind='API'
            selected={selectedIds.has(api.id)}
            onToggle={() => onToggle(api.id)}
          />
        ))}
      </div>
      )}
    </div>
  )
}

function SelectorRow({
  icon,
  name,
  kind,
  selected,
  onToggle,
}: {
  icon: React.ReactNode
  name: string
  kind: string
  selected: boolean
  onToggle: () => void
}) {
  return (
    <button
      type='button'
      onClick={onToggle}
      className={cn(
        'flex items-center gap-2 rounded-lg border px-3 py-2 text-start text-sm transition-colors',
        selected
          ? 'border-primary ring-primary/20 ring-2'
          : 'hover:bg-muted'
      )}
    >
      <span className='text-muted-foreground shrink-0'>{icon}</span>
      <span className='min-w-0 flex-1 truncate font-medium'>{name}</span>
      <Badge variant='outline'>{kind}</Badge>
      {selected && <Check aria-hidden='true' className='text-primary size-4 shrink-0' />}
    </button>
  )
}
