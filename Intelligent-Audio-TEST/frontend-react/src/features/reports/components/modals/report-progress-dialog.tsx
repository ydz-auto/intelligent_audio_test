/**
 * 生成 / 重新生成进度 Dialog（规范 §5.9，report:read）：进度条 + 状态文案
 * （pending→generating→completed/failed）。mock 演示：interval 模拟轮询
 * GET /reports/{id}/progress 至 completed → 页面跳转报告查看。
 */
import { CheckCircle2, LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface ReportProgressDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  reportId: number
  onComplete: (reportId: number) => void
}

const STATUS_TEXT: Record<string, string> = {
  pending: '排队中...',
  generating: '正在生成报告...',
  completed: '生成完成',
  failed: '生成失败',
}

export function ReportProgressDialog({
  open,
  onOpenChange,
  reportId,
  onComplete,
}: ReportProgressDialogProps) {
  const [progress, setProgress] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  useEffect(() => {
    if (!open) {
      if (timerRef.current) clearInterval(timerRef.current)
      setProgress(0)
      return
    }
    // TODO(API 接线): GET /reports/{id}/progress 指数退避轮询（+ Socket.IO report_generated 加速）
    setProgress(8)
    timerRef.current = setInterval(() => {
      setProgress((prev) => {
        const next = prev + (prev < 60 ? 22 : 100 - prev)
        if (next >= 100) {
          if (timerRef.current) clearInterval(timerRef.current)
          return 100
        }
        return next
      })
    }, 500)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [open, reportId])

  const done = progress >= 100

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>正在生成报告</DialogTitle>
          <DialogDescription>报告数据正在计算并落库，完成后自动跳转。</DialogDescription>
        </DialogHeader>
        <div className='space-y-3'>
          <div className='bg-muted h-2 w-full overflow-hidden rounded-full'>
            <div
              className='bg-primary h-full rounded-full transition-all duration-500'
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className='text-muted-foreground flex items-center gap-2 text-sm'>
            {done ? (
              <CheckCircle2 className='text-success size-4' />
            ) : (
              <LoaderCircle className='text-primary size-4 animate-spin' />
            )}
            {done ? STATUS_TEXT.completed : STATUS_TEXT.generating}
            <span className='ml-auto font-mono tabular-nums'>{Math.round(progress)}%</span>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          {done && (
            <Button onClick={() => onComplete(reportId)}>查看报告</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
