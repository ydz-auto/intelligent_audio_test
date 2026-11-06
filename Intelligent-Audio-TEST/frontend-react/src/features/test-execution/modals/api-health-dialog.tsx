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
  /**
   * 被测 API 的协议（A3 / INT-1791 §二.5）：gRPC / SSE 的正式连接探测归 INT-1953，
   * 后端现状按端点 URL scheme 分支（gRPC target 无 scheme → 「不支持的协议」），
   * 所以这里只给提示，不拦截、不伪造成功。缺省 null 时不显示提示（存量调用零变化）。
   */
  protocol?: string | null
}

export function ApiHealthDialog({
  open,
  onOpenChange,
  result,
  testing,
  onRetest,
  protocol,
}: ApiHealthDialogProps) {
  const online = result?.status === 'online'
  const protocolProbePending = protocol === 'grpc' || protocol === 'sse'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>连接测试结果</DialogTitle>
        </DialogHeader>

        {protocolProbePending && (
          <p className='bg-muted/50 text-muted-foreground rounded-md border p-2.5 text-xs'>
            {protocol === 'grpc' ? 'gRPC' : 'SSE'} 的正式连接探测尚未上线（INT-1953）：
            当前结果按端点 URL 判断协议，不代表该 API 可执行；请以执行期结果为准。
          </p>
        )}

        {!result ? (
          <p className='text-muted-foreground py-4 text-center text-sm'>
            {testing ? '正在测试连接…' : '暂无测试结果'}
          </p>
        ) : (
          <div className='min-w-0 space-y-4'>
            {/* INT-1632：长错误串（DNS/HTTP 异常全文）不得撑开弹窗，min-w-0 让 1fr 列可收缩 */}
            <div className='flex items-center justify-between gap-2'>
              <StatusBadge
                label={online ? '在线' : '离线'}
                variant={online ? 'success' : 'danger'}
              />
              <span className='flex shrink-0 items-center gap-2 text-sm'>
                <span className='text-muted-foreground'>健康分</span>
                <span className='text-lg font-semibold tabular-nums'>
                  {result.healthScore ?? '—'}
                </span>
              </span>
            </div>
            <Progress value={result.healthScore ?? 0} size='sm' className='h-1.5' />

            <dl className='text-muted-foreground grid min-w-0 grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs'>
              <dt className='whitespace-nowrap'>端点状态</dt>
              {/* INT-1223：api_url_status 移除，「端点状态」行绑 endpointsStatus */}
              <dd className='text-foreground min-w-0 break-all'>
                {result.endpointsStatus ?? '—'}
              </dd>
              <dt className='whitespace-nowrap'>HTTP 状态码</dt>
              <dd className='text-foreground min-w-0 font-mono break-all'>
                {result.statusCode ?? '—'}
              </dd>
              <dt className='whitespace-nowrap'>响应时间</dt>
              <dd className='text-foreground min-w-0 font-mono break-all'>
                {result.responseTime ?? '—'}
              </dd>
              <dt className='whitespace-nowrap'>错误信息</dt>
              <dd className='text-foreground min-w-0 break-all'>
                {result.error ?? '无'}
              </dd>
            </dl>

            {result.error && (
              <div className='bg-destructive/10 text-destructive min-w-0 rounded-md border border-destructive/25 p-3 text-xs break-all whitespace-pre-wrap'>
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
