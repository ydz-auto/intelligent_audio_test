/**
 * 清除日志 Dialog（features/logs；17_配置运维.md §4.7/§7.10，sm:max-w-md，log:manage + destructive）。
 * 「清除 {before_datetime} 之前」的日志 + 「保留已标记日志」Switch（keepMarked 默认开）
 * + 说明「清除操作不可恢复。标记过的日志将保留」→ POST /logs/clear{before_datetime, keep_marked}。
 */
import { useState } from 'react'

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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

export type LogClearDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 统计推算的将清除条数（可选；未提供时仅展示保留说明） */
  totalCount?: number
  pending: boolean
  onClear: (beforeDatetime: string, keepMarked: boolean) => void
}

export function LogClearDialog({
  open,
  onOpenChange,
  totalCount,
  pending,
  onClear,
}: LogClearDialogProps) {
  const [beforeDatetime, setBeforeDatetime] = useState('')
  const [keepMarked, setKeepMarked] = useState(true)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>清除日志</DialogTitle>
          <DialogDescription>按时间点清除日志，此操作不可恢复。</DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 py-1'>
          <div className='grid gap-1.5'>
            <Label htmlFor='log-clear-before'>清除该时间点之前的日志</Label>
            <Input
              id='log-clear-before'
              type='datetime-local'
              className='h-8'
              value={beforeDatetime}
              onChange={(event) => setBeforeDatetime(event.target.value)}
            />
            <p className='text-muted-foreground text-xs'>留空表示清除全部日志</p>
          </div>
          <div className='flex items-center justify-between gap-2'>
            <div className='grid gap-0.5'>
              <Label htmlFor='log-clear-keep-marked' className='text-sm'>
                保留已标记日志
              </Label>
              <p className='text-muted-foreground text-xs'>标记过的日志将保留</p>
            </div>
            <Switch
              id='log-clear-keep-marked'
              checked={keepMarked}
              onCheckedChange={setKeepMarked}
              size='sm'
            />
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant='outline' size='sm'>取消</Button>} />
          <Button
            size='sm'
            variant='destructive'
            disabled={pending}
            onClick={() => onClear(beforeDatetime, keepMarked)}
          >
            {totalCount !== undefined
              ? `清除 ${totalCount.toLocaleString()} 条日志`
              : '清除日志'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
