/**
 * 实时监控配置 Dialog（features/logs；17_配置运维.md §7.11，sm:max-w-md，log:websocket）。
 * 主通道 WS/Socket.IO /ws/logs（subscribe_task 订阅任务 + set_filter 过滤）+ 轮询间隔
 * Select[2s·5s·10s·30s·60s]（仅 WS 兜底降级时生效）+ 自动滚动 Switch + 新日志计数 toast Switch。
 */
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
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

const POLL_INTERVAL_OPTIONS = [
  { value: '2000', label: '2s' },
  { value: '5000', label: '5s' },
  { value: '10000', label: '10s' },
  { value: '30000', label: '30s' },
  { value: '60000', label: '60s' },
] as const

export type RealtimeConfigDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  pollIntervalMs: number
  onPollIntervalChange: (ms: number) => void
  autoScroll: boolean
  onAutoScrollChange: (value: boolean) => void
  toastEnabled: boolean
  onToastEnabledChange: (value: boolean) => void
}

export function RealtimeConfigDialog({
  open,
  onOpenChange,
  pollIntervalMs,
  onPollIntervalChange,
  autoScroll,
  onAutoScrollChange,
  toastEnabled,
  onToastEnabledChange,
}: RealtimeConfigDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>实时监控配置</DialogTitle>
          <DialogDescription>主通道 WS/Socket.IO /ws/logs，WS 不可用时降级轮询</DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 py-1'>
          <div className='grid items-center gap-2 sm:grid-cols-[auto_1fr]'>
            <Label htmlFor='log-realtime-poll' className='text-sm'>
              轮询间隔
            </Label>
            <Select
              value={String(pollIntervalMs)}
              onValueChange={(value) => onPollIntervalChange(Number(value ?? 5000))}
            >
              <SelectTrigger id='log-realtime-poll' size='sm'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {POLL_INTERVAL_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='flex items-center justify-between gap-2'>
            <Label htmlFor='log-realtime-autoscroll' className='text-sm'>
              自动滚动
            </Label>
            <Switch
              id='log-realtime-autoscroll'
              checked={autoScroll}
              onCheckedChange={onAutoScrollChange}
              size='sm'
            />
          </div>
          <div className='flex items-center justify-between gap-2'>
            <Label htmlFor='log-realtime-toast' className='text-sm'>
              新日志计数 toast
            </Label>
            <Switch
              id='log-realtime-toast'
              checked={toastEnabled}
              onCheckedChange={onToastEnabledChange}
              size='sm'
            />
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant='outline' size='sm'>完成</Button>} />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
