/**
 * 日志下载进度 Dialog（15_报告域.md §4.10）：正在下载日志 + 进度% + 已下载·总大小 + 速度。
 * mock 演示：桩 resolve 后按估算大小模拟 0→100 进度（约 1.8s），完成回调关闭。
 * TODO(API 接线): 下载走 XMLHttpRequest 进度事件 / fetch ReadableStream，接真实速率。
 */
import { CheckCircle2, LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface LogDownloadProgressDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 用例名（日志归属） */
  caseName: string
  /** 日志总大小（bytes） */
  totalSize: number
  onComplete: () => void
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(1)} ${units[unit]}`
}

export function LogDownloadProgressDialog({
  open,
  onOpenChange,
  caseName,
  totalSize,
  onComplete,
}: LogDownloadProgressDialogProps) {
  const [progress, setProgress] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  useEffect(() => {
    if (!open) {
      if (timerRef.current) clearInterval(timerRef.current)
      setProgress(0)
      return
    }
    timerRef.current = setInterval(() => {
      setProgress((prev) => {
        const next = prev + 5 + Math.round(Math.random() * 8)
        if (next >= 100) {
          if (timerRef.current) clearInterval(timerRef.current)
          return 100
        }
        return next
      })
    }, 90)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [open])

  const done = progress >= 100
  const downloaded = (totalSize * progress) / 100
  // 速度估算：总耗时 ≈ 90ms × 20 步 ≈ 1.8s
  const speed = done ? 0 : downloaded / 1.8

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>下载日志</DialogTitle>
          <DialogDescription>正在下载「{caseName}」的执行日志，请稍候。</DialogDescription>
        </DialogHeader>
        <div className='space-y-3'>
          <div className='bg-muted h-2 w-full overflow-hidden rounded-full'>
            <div
              className='bg-primary h-full rounded-full transition-all duration-100'
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className='text-muted-foreground flex items-center gap-2 text-sm'>
            {done ? (
              <CheckCircle2 className='text-success size-4' />
            ) : (
              <LoaderCircle className='text-primary size-4 animate-spin' />
            )}
            <span>{done ? '下载完成' : '正在下载日志'}</span>
            <span className='ml-auto font-mono tabular-nums'>{Math.round(progress)}%</span>
          </div>
          <div className='text-muted-foreground flex items-center justify-between text-xs tabular-nums'>
            <span>
              {formatBytes(downloaded)} / {formatBytes(totalSize)}
            </span>
            <span>{done ? '—' : `${formatBytes(speed)}/s`}</span>
          </div>
        </div>
        {done && (
          <div className='mt-3 flex justify-end'>
            <Button size='sm' onClick={onComplete}>
              完成
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
