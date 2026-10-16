/**
 * 日志下载进度 Dialog（15_报告域.md §4.10：正在下载日志 + 进度% + 大小 + 速度）。
 */
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface LogDownloadProgressDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  size?: number
}

export function LogDownloadProgressDialog({
  open,
  onOpenChange,
  size = 380,
}: LogDownloadProgressDialogProps) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    if (!open) {
      setProgress(0)
      return
    }
    const timer = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          clearInterval(timer)
          return 100
        }
        return Math.min(100, p + 8)
      })
    }, 80)
    return () => clearInterval(timer)
  }, [open])

  const downloaded = Math.round((size * progress) / 100)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>正在下载日志</DialogTitle>
        </DialogHeader>
        <div className='space-y-3'>
          <div className='bg-muted h-2 w-full overflow-hidden rounded-full'>
            <div
              className='bg-primary h-full rounded-full transition-all duration-500'
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className='text-muted-foreground flex items-center justify-between text-xs tabular-nums'>
            <span>{progress}%</span>
            <span>
              {downloaded} / {size} KB
            </span>
            <span>{progress > 0 ? `${(progress * 1.2).toFixed(0)} KB/s` : '—'}</span>
          </div>
          {progress >= 100 && (
            <div className='flex justify-end'>
              <Button size='sm' onClick={() => onOpenChange(false)}>
                完成
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
