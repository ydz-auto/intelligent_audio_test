import { RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'

import { useServiceHealth } from '@/application/about/useServiceHealth'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import type { ServiceTone } from '@/domain/models/about'
import { cn } from '@/lib/utils'

/**
 * 版本与服务状态卡（06_关于.md §3.1.1）：
 * /health 进入拉一次 + 刷新 icon（无轮询）；网关/认证/版本三态徽章；
 * 平台版本统一取 /health version，失败 → 「—」+ Badge「检测中」；
 * 整卡请求失败 → Alert「服务状态检测失败，请稍后重试或联系管理员。」（§4.4）。
 */

/** 三态徽章：正常（success 软底）/ 异常（destructive 软底）/ 检测中（muted） */
function StatusBadge({
  tone,
  children,
}: {
  tone: ServiceTone
  children: ReactNode
}) {
  if (tone === 'destructive') {
    return <Badge variant='destructive'>{children}</Badge>
  }
  return (
    <Badge
      className={cn(
        tone === 'success'
          ? 'bg-success/10 text-success'
          : 'bg-muted text-muted-foreground'
      )}
    >
      {children}
    </Badge>
  )
}

const TONE_LABEL: Record<ServiceTone, string> = {
  success: '正常',
  destructive: '异常',
  muted: '检测中',
}

function StatusRow({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className='border-border/60 flex items-center justify-between gap-3 border-b py-2.5 last:border-0'>
      <span className='text-muted-foreground text-sm'>{label}</span>
      <div className='flex min-w-0 items-center gap-2'>{children}</div>
    </div>
  )
}

export function AboutStatusCard() {
  const {
    version,
    versionTone,
    gateway,
    auth,
    database,
    anyFailure,
    isLoading,
    refreshing,
    refresh,
  } = useServiceHealth()

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between gap-2 [.border-b]:pb-4'>
        <CardTitle className='text-sm font-semibold'>版本与服务状态</CardTitle>
        <Button
          variant='ghost'
          size='icon'
          className='size-8'
          aria-label={refreshing ? '正在检测服务状态' : '刷新服务状态'}
          onClick={refresh}
          disabled={refreshing}
        >
          {refreshing ? <Spinner size={16} /> : <RefreshCw aria-hidden='true' />}
        </Button>
      </CardHeader>
      <CardContent className='space-y-0'>
        {isLoading ? (
          <div className='space-y-3 py-1'>
            <Skeleton className='h-4 w-full' />
            <Skeleton className='h-4 w-full' />
            <Skeleton className='h-4 w-[80%]' />
          </div>
        ) : (
          <>
            <StatusRow label='平台版本'>
              <span className='text-sm tabular-nums'>{version}</span>
              <StatusBadge tone={versionTone}>{TONE_LABEL[versionTone]}</StatusBadge>
            </StatusRow>
            <StatusRow label={gateway.label}>
              <span className='text-muted-foreground text-xs tabular-nums'>
                {gateway.value}
              </span>
              <StatusBadge tone={gateway.tone}>{gateway.badge}</StatusBadge>
            </StatusRow>
            <StatusRow label={auth.label}>
              <span className='text-muted-foreground text-xs tabular-nums'>
                {auth.value}
              </span>
              <StatusBadge tone={auth.tone}>{auth.badge}</StatusBadge>
            </StatusRow>
            <StatusRow label='数据库'>
              <span className='text-muted-foreground text-xs tabular-nums'>
                {database ?? '—'}
              </span>
            </StatusRow>
          </>
        )}

        <p className='text-muted-foreground mt-3 text-xs leading-5'>
          服务状态来自平台健康检查接口，反映网关与认证服务可达性。
        </p>

        {anyFailure && (
          <Alert variant='destructive' className='mt-3'>
            <AlertDescription>
              服务状态检测失败，请稍后重试或联系管理员。
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
