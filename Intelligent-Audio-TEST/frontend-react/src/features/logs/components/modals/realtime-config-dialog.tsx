/**
 * 实时监控配置弹窗（interfaces 层；17_配置运维.md §7.11，Dialog sm:max-w-md，
 * log:websocket）。
 * 主通道 WS/Socket.IO /ws/logs（subscribe_task + set_filter[levels/modules/keyword/
 * task_id]，§4.6，INT-928 接线）——WS 已连即纯 WS 主通道；WS 不可用时降级
 * POST /logs/refresh 轮询兜底（log:manage）：轮询间隔 Select[2s/5s/10s/30s/60s]
 * （默认跟随 VITE_LOG_POLL_IDLE_MAX_MS 语义，空闲指数退避至 30s）+ 自动滚动 Switch +
 * 新日志计数 toast Switch。
 */
import { useMemo } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import type { LogRealtimeConfig } from '@/domain/models/log'
import { REALTIME_POLL_INTERVALS } from '@/features/logs/constants'

export type RealtimeConfigDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: LogRealtimeConfig
  onConfigChange: (patch: Partial<LogRealtimeConfig>) => void
}

export function RealtimeConfigDialog(props: RealtimeConfigDialogProps) {
  const { config } = props

  const intervalSeconds = useMemo(
    () => Math.round(config.pollIntervalMs / 1000),
    [config.pollIntervalMs]
  )

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>实时监控配置</DialogTitle>
          <DialogDescription>
            主通道 WS/Socket.IO /ws/logs（task_log 增量插顶）；WS 不可用时降级轮询兜底（需 log:manage）。
          </DialogDescription>
        </DialogHeader>

        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label htmlFor='realtime-poll-interval'>轮询间隔</Label>
            <Select
              value={String(intervalSeconds)}
              onValueChange={(v) =>
                props.onConfigChange({ pollIntervalMs: Number(v ?? 5) * 1000 })
              }
            >
              <SelectTrigger id='realtime-poll-interval' className='w-32' size='sm'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REALTIME_POLL_INTERVALS.map((option) => (
                  <SelectItem key={option.value} value={String(option.value / 1000)}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className='text-muted-foreground text-xs'>
              无新日志时轮询自动放缓，上限 30s（VITE_LOG_POLL_IDLE_MAX_MS 语义）
            </p>
          </div>

          <div className='flex items-center justify-between gap-2'>
            <div>
              <Label htmlFor='realtime-auto-scroll'>自动滚动</Label>
              <p className='text-muted-foreground text-xs'>新日志到达自动滚到列表底部</p>
            </div>
            <Switch
              id='realtime-auto-scroll'
              checked={config.autoScroll}
              onCheckedChange={(v) => props.onConfigChange({ autoScroll: v })}
              aria-label='自动滚动'
            />
          </div>

          <div className='flex items-center justify-between gap-2'>
            <div>
              <Label htmlFor='realtime-notify'>新日志计数 toast</Label>
              <p className='text-muted-foreground text-xs'>
                {'新日志到达时提示「新收到 {n} 条日志」'}
              </p>
            </div>
            <Switch
              id='realtime-notify'
              checked={config.notifyNewLogs}
              onCheckedChange={(v) => props.onConfigChange({ notifyNewLogs: v })}
              aria-label='新日志计数 toast'
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            size='sm'
            onClick={() => props.onOpenChange(false)}
          >
            完成
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
