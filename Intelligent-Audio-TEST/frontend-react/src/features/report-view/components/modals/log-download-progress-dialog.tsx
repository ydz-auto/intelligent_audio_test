/**
 * 日志下载进度 Dialog（15_报告域.md §4.10b，INT-1067）。
 * 受控展示：正在下载日志（{n} 个文件）+ 进度% + 已下载·所选总量 + 速度。
 * 进度数据由调用方从真实下载（fetch ReadableStream 逐块读取）计算后传入，
 * 照现形态（保留原 Dialog），按所选总量与真实速率推进。
 */
import { CheckCircle2, LoaderCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { formatBytes } from './log-format'

interface LogDownloadProgressDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 用例名（日志归属） */
  caseName: string
  /** 所选文件数（正在下载日志（{n} 个文件）） */
  fileCount: number
  /** 已下载字节数 */
  downloaded: number
  /** 总字节数（所选文件合计 / Content-Length） */
  totalSize: number
  /** 下载速度（bytes/s，500ms 采样） */
  speed: number
  /** 是否下载完成（显示「完成」钮） */
  done: boolean
  onComplete: () => void
}

export function LogDownloadProgressDialog({
  open,
  onOpenChange,
  caseName,
  fileCount,
  downloaded,
  totalSize,
  speed,
  done,
  onComplete,
}: LogDownloadProgressDialogProps) {
  const progress = totalSize > 0 ? Math.min(100, Math.round((downloaded / totalSize) * 100)) : 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md' showCloseButton={done}>
        <DialogHeader>
          <DialogTitle>下载日志</DialogTitle>
          <DialogDescription>
            正在下载「{caseName}」的执行日志（{fileCount} 个文件），请稍候。
          </DialogDescription>
        </DialogHeader>
        <div className='space-y-3'>
          <div className='bg-muted h-2 w-full overflow-hidden rounded-full'>
            <div
              className='bg-primary h-full rounded-full transition-all duration-150'
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className='text-muted-foreground flex items-center gap-2 text-sm'>
            {done ? (
              <CheckCircle2 className='text-success size-4' aria-hidden='true' />
            ) : (
              <LoaderCircle className='text-primary size-4 animate-spin' aria-hidden='true' />
            )}
            <span>{done ? '下载完成' : '正在下载日志'}</span>
            <span className='ml-auto font-mono tabular-nums'>{progress}%</span>
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
