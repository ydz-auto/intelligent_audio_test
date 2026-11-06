/**
 * 日志下载进度 Dialog（15_报告域.md §4.10b，INT-1067）。
 * 受控展示：正在下载日志（{n} 个文件）+ 进度% + 已下载·传输总量 + 速度。
 * 进度数据由调用方从真实下载（fetch ReadableStream 逐块读取）计算后传入。
 * INT-1905 P3-5：分子（已接收字节）与分母（传输总量 Content-Length）同口径——都是压缩后
 * 的 zip 字节，不再拿未压缩的文件大小合计当分母；传输总量未知时退化为不确定进度条。
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
  /** 已下载字节数（传输层：压缩后的 zip 字节） */
  downloaded: number
  /** 传输总字节数（Content-Length / presigned 信封 size；未知为 0） */
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
  /** 进度百分比；分母未知（totalSize=0）时为 null → 不确定进度条 */
  const progress =
    totalSize > 0 ? Math.min(100, Math.round((downloaded / totalSize) * 100)) : done ? 100 : null

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
          <div
            role='progressbar'
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress ?? undefined}
            aria-label='日志下载进度'
            className='bg-muted relative h-2 w-full overflow-hidden rounded-full'
          >
            {progress === null ? (
              /* 传输总量未知（无 Content-Length）：不确定进度条 */
              <div className='bg-primary/50 h-full w-1/2 animate-pulse rounded-full' />
            ) : (
              <div
                className='bg-primary h-full rounded-full transition-all duration-150'
                style={{ width: `${progress}%` }}
              />
            )}
          </div>
          <div className='text-muted-foreground flex items-center gap-2 text-sm'>
            {done ? (
              <CheckCircle2 className='text-success size-4' aria-hidden='true' />
            ) : (
              <LoaderCircle className='text-primary size-4 animate-spin' aria-hidden='true' />
            )}
            <span>{done ? '下载完成' : '正在下载日志'}</span>
            {progress !== null && (
              <span className='ml-auto font-mono tabular-nums'>{progress}%</span>
            )}
          </div>
          <div className='text-muted-foreground flex items-center justify-between text-xs tabular-nums'>
            <span>
              {formatBytes(downloaded)}
              {totalSize > 0 ? ` / ${formatBytes(totalSize)}` : ''}
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
