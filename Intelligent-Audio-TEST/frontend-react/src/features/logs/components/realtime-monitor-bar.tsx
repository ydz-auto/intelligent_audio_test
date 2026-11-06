/**
 * 实时监控指示器（interfaces 层；17_配置运维.md §4.6 realtime-monitor-bar）。
 * 顶部 info 条：状态点（WS 主通道已连=success 脉冲 / 连接中·轮询兜底=info 脉冲 /
 * 连接中断=destructive）+「实时监控中」+ 统计（连接状态/速率 条每秒/延迟 ms，
 * font-mono tabular-nums）+ 右侧「自动滚动」Toggle +「配置」钮（§7.11 实时监控配置 Dialog）。
 * 主通道 WS/Socket.IO /ws/logs（INT-928 接线：subscribe_task/set_filter + task_log 增量插顶），
 * WS 不可用降级 POST /logs/refresh 轮询兜底（log:manage）——状态文案随连接状态映射切换。
 */
import { Activity } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type { LogRealtimeConfig } from '@/domain/models/log'
import type { LogRealtimeConnection } from '@/application/logs/useLogRealtime'

const CONNECTION_TEXT: Record<LogRealtimeConnection, { label: string; dot: string }> = {
  idle: { label: '已停止', dot: 'bg-neutral' },
  connecting: { label: '连接中', dot: 'bg-info animate-pulse' },
  ws: { label: 'WS实时', dot: 'bg-success animate-pulse' },
  polling: { label: '轮询兜底', dot: 'bg-info animate-pulse' },
  error: { label: '连接中断', dot: 'bg-destructive' },
}

export type RealtimeMonitorBarProps = {
  connection: LogRealtimeConnection
  logRate: number
  logDelay: number
  config: LogRealtimeConfig
  onAutoScrollChange: (value: boolean) => void
  onOpenConfig: () => void
}

export function RealtimeMonitorBar(props: RealtimeMonitorBarProps) {
  const status = CONNECTION_TEXT[props.connection]

  return (
    <div className='border-border/60 bg-muted/25 inline-flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border px-2.5 py-1.5 text-xs'>
      <span className='inline-flex items-center gap-1.5 font-medium'>
        <span aria-hidden='true' className={cn('size-1.5 rounded-full', status.dot)} />
        实时监控中
        <span className='text-muted-foreground'>{status.label}</span>
      </span>
      <span className='font-mono text-muted-foreground tabular-nums'>
        速率：{props.logRate.toFixed(1)} 条/秒
      </span>
      <span className='font-mono text-muted-foreground tabular-nums'>
        延迟：{props.logDelay}ms
      </span>
      <span className='inline-flex items-center gap-1.5'>
        自动滚动
        <Switch
          checked={props.config.autoScroll}
          onCheckedChange={props.onAutoScrollChange}
          size='sm'
          aria-label='自动滚动'
        />
      </span>
      <Button
        variant='ghost'
        size='sm'
        className='h-6 gap-1 text-xs'
        onClick={props.onOpenConfig}
      >
        <Activity aria-hidden='true' className='size-3' />
        配置
      </Button>
    </div>
  )
}
