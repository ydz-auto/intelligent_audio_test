/**
 * 生成 / 重新生成 / 二次对比 进度 Dialog（规范 §5.9，report:read）。INT-935 去 mock 计时：
 * - reportId（同步生成：compare）→ 指数退避轮询 GET /reports/{id}/progress 至 completed
 * - taskId（异步生成：generate-task / regenerate）→ 订阅 SSE report_generated 事件取 reportId
 * - waitPromise（异步生成：secondary-compare）→ 直接 await 对比弹窗提交前已订阅的 SSE 等待
 *   （reportKey 提交前可算 → 订阅先于 POST，事件必达无竞态）
 * 完成 → 页面跳转报告查看（onComplete(reportId)）；失败/超时 → 状态文案 + 仅可关闭。
 */
import { CheckCircle2, LoaderCircle, XCircle } from 'lucide-react'
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
import { fetchReportProgress } from '@/infrastructure/api/reports-api'
import { waitForReportGenerated } from '@/application/reports/use-report-compare'

interface ReportProgressDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 同步生成报告 id（compare），存在时按 /reports/{id}/progress 轮询 */
  reportId?: number
  /** 异步生成任务 id（generate-task / regenerate），存在时订阅 report_generated */
  taskId?: number
  /** 二次对比 SSE 等待 Promise（提交前已订阅，进度弹窗直接 await；onWaitAbort 负责解绑） */
  waitPromise?: Promise<number>
  /** 取消等待（dialog 关闭/卸载时调用，终止 SSE 订阅） */
  onWaitAbort?: () => void
  onComplete: (reportId: number) => void
}

type ProgressStatus = 'pending' | 'generating' | 'completed' | 'failed'

const STATUS_TEXT: Record<ProgressStatus, string> = {
  pending: '排队中...',
  generating: '正在生成报告...',
  completed: '生成完成',
  failed: '生成失败',
}

/** 进度轮询指数退避（500ms × 2^n 封顶 8s；Vue 参考指数退避口径） */
const POLL_BASE_MS = 500
const POLL_MAX_MS = 8_000
/** 轮询总超时（报告生成慢时兜底失败态，避免无限轮询） */
const POLL_TOTAL_TIMEOUT_MS = 300_000

export function ReportProgressDialog({
  open,
  onOpenChange,
  reportId,
  taskId,
  waitPromise,
  onWaitAbort,
  onComplete,
}: ReportProgressDialogProps) {
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<ProgressStatus>('pending')
  const [error, setError] = useState('')
  /** 异步链路 SSE 事件回传的真实报告 id（reportId 轮询链路复用入参） */
  const [resolvedReportId, setResolvedReportId] = useState<number | undefined>(undefined)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // 关闭/重开重置
  useEffect(() => {
    if (!open) {
      if (timerRef.current) clearTimeout(timerRef.current)
      setProgress(0)
      setStatus('pending')
      setError('')
      setResolvedReportId(undefined)
    }
  }, [open])

  // reportId → 轮询 GET /reports/{id}/progress
  useEffect(() => {
    if (!open || !(typeof reportId === 'number' && reportId > 0)) return
    let cancelled = false
    let attempts = 0
    const startedAt = Date.now()

    const schedule = (delay: number) => {
      if (cancelled) return
      timerRef.current = setTimeout(() => void poll(), delay)
    }

    const poll = async () => {
      if (cancelled) return
      try {
        const p = await fetchReportProgress(reportId)
        if (cancelled) return
        setProgress(Math.max(0, Math.min(100, p.progress)))
        if (p.status === 'completed') {
          setStatus('completed')
          setProgress(100)
          return
        }
        if (p.status === 'failed') {
          setStatus('failed')
          setError('报告生成失败')
          return
        }
        attempts += 1
        schedule(Math.min(POLL_BASE_MS * 2 ** attempts, POLL_MAX_MS))
      } catch {
        if (cancelled) return
        attempts += 1
        if (Date.now() - startedAt > POLL_TOTAL_TIMEOUT_MS) {
          setStatus('failed')
          setError('报告生成超时，请稍后在报告列表查看')
          return
        }
        schedule(Math.min(POLL_BASE_MS * 2 ** attempts, POLL_MAX_MS))
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [open, reportId])

  // taskId（generate-task / regenerate）→ 订阅 report_generated。
  // 兜底路径：waitPromise 存在时外层（dialog/index）已提交前预订阅并回传，本 effect 跳过，
  // 避免二次订阅（INT-935 返工 P2：taskId 补订阅晚于 POST 会有快速失败事件竞态，仅无 waitPromise 时启用）
  useEffect(() => {
    if (!open || waitPromise || !(typeof taskId === 'number' && taskId > 0)) return
    const controller = new AbortController()
    let cancelled = false
    setStatus('generating')
    void (async () => {
      try {
        const id = await waitForReportGenerated({ taskId }, { signal: controller.signal })
        if (cancelled) return
        setResolvedReportId(id)
        setStatus('completed')
        setProgress(100)
      } catch (err) {
        if (cancelled) return
        setStatus('failed')
        setError(err instanceof Error ? err.message : '报告生成失败')
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [open, taskId, waitPromise])

  // waitPromise（secondary-compare / generate-task / regenerate）→ 直接 await 提交前已订阅的 SSE 等待
  useEffect(() => {
    if (!open || !waitPromise) return
    let cancelled = false
    setStatus('generating')
    void waitPromise
      .then((id) => {
        if (cancelled) return
        setResolvedReportId(id)
        setStatus('completed')
        setProgress(100)
      })
      .catch((err) => {
        if (cancelled) return
        setStatus('failed')
        setError(err instanceof Error ? err.message : '报告生成失败')
      })
    return () => {
      cancelled = true
      onWaitAbort?.()
    }
  }, [open, waitPromise, onWaitAbort])

  const done = status === 'completed'
  const failed = status === 'failed'

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
            ) : failed ? (
              <XCircle className='text-destructive size-4' />
            ) : (
              <LoaderCircle className='text-primary size-4 animate-spin' />
            )}
            {failed ? STATUS_TEXT.failed : done ? STATUS_TEXT.completed : STATUS_TEXT[status]}
            <span className='ml-auto font-mono tabular-nums'>{Math.round(progress)}%</span>
          </div>
          {failed && error && <p className='text-destructive text-sm'>{error}</p>}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            {failed ? '关闭' : '取消'}
          </Button>
          {done && (
            <Button
              onClick={() => {
                const id = resolvedReportId ?? reportId
                if (typeof id === 'number' && id > 0) onComplete(id)
              }}
            >
              查看报告
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
