/**
 * 第三方账号绑定（13_个人中心.md §3.5.2）：对位 newAPI account-bindings.tsx 版式，
 * 数据源为本平台动态 OAuth 提供方（公开）+ 绑定列表；绑定/解绑交互 + 解绑确认框。
 * 认证接线 INT-606：绑定走真实 OAuth 授权跳转（intent=bind）；回调携
 * bind_ticket 回个人中心（INT-358 消化）；解绑流程可用：
 * ConfirmDialog → unbind mutation → toast + invalidate。
 */
import { Link2, Unlink } from 'lucide-react'
import { useState } from 'react'

import { useOAuthBindings } from '@/application/profile/use-oauth-bindings'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { authApi } from '@/infrastructure/api/authApi'

import {
  BINDINGS_EMPTY_DESCRIPTION,
  BINDINGS_EMPTY_TITLE,
  BINDINGS_SECTION_DESCRIPTION,
  BINDINGS_SECTION_TITLE,
  BINDING_BOUND_BADGE,
  BINDING_PROCESSING_ARIA,
  BINDING_UNBOUND_VALUE,
  BIND_BUTTON,
  UNBIND_BUTTON,
  UNBIND_CONFIRM_ACTION,
  UNBIND_CONFIRM_CANCEL,
  UNBIND_CONFIRM_TITLE,
} from '../constants'

/** 内联提供方图标（github 公版 SVG；其余 Link2 兜底，§3.5.2） */
function ProviderIcon({ icon }: { icon: string }) {
  if (icon === 'github') {
    return (
      <svg viewBox='0 0 24 24' fill='currentColor' className='size-4' aria-hidden='true'>
        <path d='M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12' />
      </svg>
    )
  }
  return <Link2 aria-hidden='true' className='size-4' />
}

export function AccountBindings() {
  const { rows, isLoading, bindingsLocked, unbind } = useOAuthBindings()
  /** 待解绑提供方 id（ConfirmDialog 状态；null=关闭） */
  const [unbindTarget, setUnbindTarget] = useState<string | null>(null)

  const unbindingProvider = rows.find((row) => row.provider.id === unbindTarget)
    ?.provider

  function handleBind(providerId: string) {
    if (bindingsLocked) return
    const provider = rows.find((row) => row.provider.id === providerId)?.provider
    if (!provider) return
    // 整页 302 → /auth/oauth/{slug}/authorize?intent=bind（state 签名；回调携
    // bind_ticket 回 /#/AccountSettings?bind_ticket=… 由个人中心卡消化）
    authApi.beginOAuthAuthorize(provider.slug, 'bind')
  }

  function handleConfirmUnbind() {
    if (!unbindTarget) return
    unbind(unbindTarget)
    setUnbindTarget(null)
  }

  if (isLoading) {
    return (
      <div className='grid gap-2'>
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className='flex items-center justify-between gap-2 rounded-lg border px-2.5 py-2'
          >
            <div className='flex items-center gap-2.5'>
              <Skeleton className='size-8 rounded-md' />
              <div className='grid gap-1'>
                <Skeleton className='h-4 w-24' />
                <Skeleton className='h-3 w-32' />
              </div>
            </div>
            <Skeleton className='h-7 w-14' />
          </div>
        ))}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <Empty className='py-6'>
        <EmptyContent>
          <EmptyTitle>{BINDINGS_EMPTY_TITLE}</EmptyTitle>
          <EmptyDescription>{BINDINGS_EMPTY_DESCRIPTION}</EmptyDescription>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <div className='grid gap-2'>
      <p className='text-sm font-semibold'>{BINDINGS_SECTION_TITLE}</p>
      <p className='text-muted-foreground text-xs'>{BINDINGS_SECTION_DESCRIPTION}</p>
      <ul className='grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3'>
        {rows.map(({ provider, binding }) => (
          <li
            key={provider.id}
            className='flex items-center justify-between gap-2 rounded-lg border px-2.5 py-2'
          >
            <div className='flex min-w-0 items-center gap-2'>
              <span className='bg-muted rounded-md p-1.5'>
                <ProviderIcon icon={provider.icon} />
              </span>
              <div className='grid min-w-0 gap-0.5'>
                <div className='flex items-center gap-1.5'>
                  <span className='truncate text-sm font-medium'>
                    {provider.name}
                  </span>
                  {binding && (
                    <Badge className='bg-success/10 text-success'>
                      {BINDING_BOUND_BADGE}
                    </Badge>
                  )}
                </div>
                <span className='text-muted-foreground truncate font-mono text-xs'>
                  {binding ? binding.providerUserId : BINDING_UNBOUND_VALUE}
                </span>
              </div>
            </div>
            {binding ? (
              <Button
                type='button'
                variant='ghost'
                size='sm'
                disabled={bindingsLocked}
                aria-label={
                  bindingsLocked ? BINDING_PROCESSING_ARIA : `解绑 ${provider.name}`
                }
                onClick={() => setUnbindTarget(provider.id)}
                className='h-7 shrink-0 px-2.5 text-xs text-destructive'
              >
                <Unlink aria-hidden='true' />
                {UNBIND_BUTTON}
              </Button>
            ) : (
              <Button
                type='button'
                variant='outline'
                size='sm'
                disabled={bindingsLocked}
                aria-label={
                  bindingsLocked ? BINDING_PROCESSING_ARIA : `绑定 ${provider.name}`
                }
                onClick={() => handleBind(provider.id)}
                className='h-7 shrink-0 px-2.5 text-xs'
              >
                {BIND_BUTTON}
              </Button>
            )}
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={unbindTarget !== null}
        onOpenChange={(open) => {
          if (!open) setUnbindTarget(null)
        }}
        title={UNBIND_CONFIRM_TITLE}
        desc={
          unbindingProvider
            ? `确认解绑「${unbindingProvider.name}」？解绑后将无法使用该第三方账号登录。`
            : ''
        }
        confirmText={UNBIND_CONFIRM_ACTION}
        cancelBtnText={UNBIND_CONFIRM_CANCEL}
        destructive
        handleConfirm={handleConfirmUnbind}
      />
    </div>
  )
}
