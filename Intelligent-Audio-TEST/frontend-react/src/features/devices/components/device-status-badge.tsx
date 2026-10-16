/**
 * 设备状态徽章（16_设备域.md §3.4/§7；INT-487「测试中」占用叠加态）。
 * 五态状态机走 StatusBadge（online=success「在线」/offline=neutral「离线」/connecting=info
 * 「连接中」/disconnecting=warning「断开中」/error=destructive「错误」）。
 * 「测试中」为占用叠加态：设备被测试任务占用时状态位叠加 info 徽章 + 脉冲动画（Activity
 * 图标），不占五态机枚举/筛选/统计（§3.4 注 / INT-487）。
 */
import { Activity } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { StatusBadge, type StatusVariant } from '@/features/dashboard/components/ui/status-badge'
import { cn } from '@/lib/utils'
import {
  DEVICE_FIVE_STATE_META,
  type DeviceFiveState,
} from '@/domain/models/testDevice'

const TONE_TO_VARIANT: Record<DeviceFiveState, StatusVariant> = {
  online: 'success',
  offline: 'neutral',
  connecting: 'info',
  disconnecting: 'warning',
  error: 'danger',
}

export function DeviceStatusBadge({
  status,
  occupied,
  className,
}: {
  status: DeviceFiveState | null
  /** 「测试中」占用叠加态（INT-487） */
  occupied: boolean
  className?: string
}) {
  if (!status) return <span className='text-muted-foreground'>—</span>
  const meta = DEVICE_FIVE_STATE_META[status]
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <StatusBadge label={meta.label} variant={TONE_TO_VARIANT[status]} size='sm' />
      {occupied && (
        <Badge
          variant='outline'
          className='gap-1.5 border-info/40 bg-info/10 px-2 font-normal text-info animate-pulse'
        >
          <Activity aria-hidden='true' className='size-3 animate-pulse' />
          测试中
        </Badge>
      )}
    </span>
  )
}
