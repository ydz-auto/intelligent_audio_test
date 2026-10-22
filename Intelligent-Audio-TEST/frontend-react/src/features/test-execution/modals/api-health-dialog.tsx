/**
 * API 连接测试结果弹窗（§5.4；interfaces/features/test-execution/modals；Dialog max-w-sm）。
 * 标题「连接测试结果」+ 状态徽章（在线=success/离线=destructive）+ 健康分
 * （大号 tabular-nums + Progress）+ 键值行（端点状态/HTTP 状态码/响应时间/错误信息——
 * ApiHealthCheckResult 字段照 DTO）；「重新测试」ghost 钮（api_config:test）。
 */
import { PlugZap } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/features/tasks/components/ui/progress'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { ApiHealthCheckResult } from '@/domain/models/apiConfig'

interface ApiHealthDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: ApiHealthCheckResult | null
  testing: boolean
  onRetest: () => void
}

export function ApiHealthDialog({
  open,
  onOpenChange,
  result,
  testing,
  onRetest,
}: ApiHealthDialogProps) {
  const online = result?.status === 'online'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>连接测试结果</DialogTitle>
        </DialogHeader>

        {!result ? (
          <p className='text-muted-foreground py-4 text-center text-sm'>
            {testing ? '正在测试连接…' : '暂无测试结果'}
          </p>
        ) : (
          <div className='space-y-4'>
            <div className='flex items-center justify-between'>
              <StatusBadge
                label={online ? '在线' : '离线'}
                variant={online ? 'success' : 'danger'}
              />
              <span className='flex items-center gap-2 text-sm'>
                <span className='text-muted-foreground'>健康分</span>
                <span className='text-lg font-semibold tabular-nums'>
                  {result.healthScore ?? '—'}
                </span>
              </span>
            </div>
            <Progress value={result.healthScore ?? 0} size='sm' className='h-1.5' />

            <dl className='text-muted-foreground grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs'>
              <dt>端点状态</dt>
              {/* INT-1223：api_url_status 移除，「端点状态」行绑 endpointsStatus */}
              <dd className='text-foreground'>{result.endpointsStatus ?? '—'}</dd>
              <dt>HTTP 状态码</dt>
              <dd className='text-foreground font-mono'>{result.statusCode ?? '—'}</dd>
              <dt>响应时间</dt>
              <dd className='text-foreground font-mono'>{result.responseTime ?? '—'}</dd>
              <dt>错误信息</dt>
              <dd className='text-foreground'>{result.error ?? '无'}</dd>
            </dl>

            {result.error && (
              <div className='bg-destructive/10 text-destructive rounded-md border border-destructive/25 p-3 text-xs'>
                {result.error}
              </div>
            )}

            <div className='flex justify-end'>
              <Button variant='ghost' size='sm' disabled={testing} onClick={onRetest}>
                <PlugZap aria-hidden='true' className={testing ? 'size-3.5 animate-pulse' : 'size-3.5'} />
                {testing ? '测试中…' : '重新测试'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
