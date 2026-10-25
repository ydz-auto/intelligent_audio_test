/**
 * 评估维度页 API 健康测试结果弹窗（features/evaluation/modals；11_用例域.md §5.5）。
 * Dialog sm:max-w-lg：标题「API健康测试结果」+ 头部维度名 + 总状态 StatusBadge
 * （在线=success/离线=danger）+ 端点明细表（端点 URL mono truncate / 状态徽章 /
 * 响应时间 tabular-nums / 信息）；主钮「关闭」。打开时自动触发健康探测（门槛 evaluation:read）。
 * 无端点（results 为空）时走空态文案，不显示「总状态 在线」（INT-1816 P3-3）。
 */
import { useEffect } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type {
  Dimension,
  HealthCheckResultItem,
} from '@/domain/models/evaluationDimension'
import type { UseMutationResult } from '@tanstack/react-query'

type HealthMutation = UseMutationResult<
  { results: HealthCheckResultItem[]; overallStatus: string },
  unknown,
  Dimension
>

export function HealthTestDialog({
  open,
  onOpenChange,
  dimension,
  healthTest,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  dimension: Dimension | null
  healthTest: HealthMutation
}) {
  useEffect(() => {
    if (open && dimension && !healthTest.isPending) {
      healthTest.mutate(dimension, {
        onError: () => toast.error('API测试失败'),
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, dimension])

  const data = healthTest.data
  // INT-1816 P3-3：后端对无端点维度返回 results=[] + overallStatus='online'，
  // 空结果不能表达成「总状态 在线」——没有可探测端点时走空态文案
  const results = data?.results ?? []
  const hasResults = results.length > 0
  const online = data?.overallStatus !== 'offline'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>API健康测试结果</DialogTitle>
          <DialogDescription>
            {dimension?.name ?? ''}
          </DialogDescription>
        </DialogHeader>

        {healthTest.isPending ? (
          <div className='flex items-center justify-center gap-2 py-8'>
            <Spinner />
            <span className='text-muted-foreground text-sm'>正在健康探测...</span>
          </div>
        ) : data && hasResults ? (
          <div className='space-y-3'>
            <div className='flex items-center gap-2'>
              <span className='text-muted-foreground text-sm'>总状态</span>
              <StatusBadge
                label={online ? '在线' : '离线'}
                variant={online ? 'success' : 'danger'}
                size='sm'
              />
            </div>
            <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
              <table className='w-full text-[13px]'>
                <thead>
                  <tr className='bg-[var(--table-header)] text-xs'>
                    <th className='px-3 py-2 text-left font-medium'>端点 URL</th>
                    <th className='px-3 py-2 text-left font-medium'>状态</th>
                    <th className='px-3 py-2 text-right font-medium'>响应时间</th>
                    <th className='px-3 py-2 text-left font-medium'>信息</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((result, index) => (
                    <tr
                      key={index}
                      className='border-border/50 hover:bg-muted/40 border-b last:border-b-0'
                    >
                      <td className='max-w-52 px-3 py-2'>
                        <span
                          className='block truncate font-mono text-xs'
                          title={result.url}
                        >
                          {result.url}
                        </span>
                      </td>
                      <td className='px-3 py-2'>
                        <StatusBadge
                          label={
                            result.status === 'online' ? '在线' : '离线'
                          }
                          variant={result.status === 'online' ? 'success' : 'danger'}
                          size='sm'
                        />
                      </td>
                      <td className='px-3 py-2 text-right tabular-nums'>
                        {result.responseTime ?? '—'}
                      </td>
                      <td className='px-3 py-2'>
                        {result.error ? (
                          <span className='text-destructive text-xs'>
                            {result.error}
                          </span>
                        ) : (
                          <span className='text-muted-foreground text-xs'>
                            {result.message ?? '—'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className='text-muted-foreground py-8 text-center text-sm'>
            {data ? '该维度未配置 API 端点，无可探测端点' : '暂无健康探测数据'}
          </p>
        )}

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
