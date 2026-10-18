/**
 * 实时监控指示器（features/logs；17_配置运维.md §4.6）。
 * 顶部 info 条：状态点（连接成功=success 脉冲 / 断开=destructive）+「实时监控中」+
 * 统计（连接/速率/延迟，font-mono tabular-nums）+「自动滚动」Toggle +「配置」钮。
 */
import { Settings2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Toggle } from '@/components/ui/toggle'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { RealtimeStatus } from '@/features/logs/hooks/use-log-realtime'
import { cn } from '@/lib/utils'

export type RealtimeIndicatorProps = {
  status: RealtimeStatus
  statusText: string
  logRate: number
  logDelay: number
  autoScroll: boolean
  onToggleAutoScroll: () => void
  onOpenConfig: () => void
}

export function LogsRealtimeIndicator({
  status,
  statusText,
  logRate,
  logDelay,
  autoScroll,
  onToggleAutoScroll,
  onOpenConfig,
}: RealtimeIndicatorProps) {
  const connected = status === 'connected' || status === 'polling'
  const pulse = status === 'connected'
  return (
    <div className='border-border/60 bg-card/50 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-1.5 text-xs'>
      <StatusBadge
        label='实时监控中'
        variant={connected ? 'success' : 'danger'}
        pulse={pulse}
        icon={undefined}
      />
      <div className='text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 font-mono tabular-nums'>
        <span>
          连接：<span className={cn(connected ? 'text-success' : 'text-destructive')}>{statusText}</span>
        </span>
        <span>速率：{logRate} 条/秒</span>
        <span>延迟：{logDelay}ms</span>
      </div>
      <div className='ml-auto flex items-center gap-1.5'>
        <Toggle
          size='sm'
          variant='outline'
          pressed={autoScroll}
          onPressedChange={onToggleAutoScroll}
          aria-label='自动滚动'
          className='h-7 gap-1 px-2 text-xs'
        >
          自动滚动
        </Toggle>
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground hover:text-foreground h-7 gap-1 px-2 text-xs'
          onClick={onOpenConfig}
        >
          <Settings2 aria-hidden='true' className='size-3.5' />
          配置
        </Button>
      </div>
    </div>
  )
}
