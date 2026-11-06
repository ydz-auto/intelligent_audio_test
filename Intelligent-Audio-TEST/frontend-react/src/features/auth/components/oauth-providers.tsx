import { toast } from 'sonner'
import { Fingerprint } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { usePublicOAuthProviders } from '@/application/auth/use-public-oauth-providers'
import { authApi } from '@/infrastructure/api/authApi'
import type { OAuthProvider } from '@/domain/models/auth'

import { OAUTH_DIVIDER_TEXT } from '../constants'

/**
 * OAuth 提供方区（对位 newAPI oauth-providers.tsx 版式，
 * 12_登录与错误页.md §3.5）：分离式分隔线 + 纵列 outline 按钮。
 * 认证接线 INT-606：数据源 GET /auth/oauth/providers 真实渲染；
 * 点击整页 302 跳 /api/v1/auth/oauth/{slug}/authorize；空列表整区不渲染。
 */

/** 内联品牌图标（lucide v1 无品牌图标；github 走公版 SVG，其余回退 Fingerprint） */
function ProviderIcon({ icon }: { icon: string }) {
  if (icon === 'github') {
    return (
      <svg viewBox='0 0 24 24' fill='currentColor' className='h-4 w-4' aria-hidden='true'>
        <path d='M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12' />
      </svg>
    )
  }
  return <Fingerprint aria-hidden='true' className='h-4 w-4' />
}

export function OAuthProviders({
  disabled = false,
  className,
}: {
  disabled?: boolean
  className?: string
}) {
  const { data: providers = [] } = usePublicOAuthProviders()

  if (providers.length === 0) return null

  function handleClick(provider: OAuthProvider) {
    // 整页 302 跳 authorize（本页跳转不新标签，INT-285 口径③）
    try {
      authApi.beginOAuthAuthorize(provider.slug)
    } catch {
      toast.error('第三方登录暂不可用，请稍后重试')
    }
  }

  return (
    <div className={className ?? 'space-y-3'}>
      <div className='relative'>
        <div className='absolute inset-0 flex items-center'>
          <span className='w-full border-t' />
        </div>
        <div className='relative flex justify-center text-xs uppercase'>
          <span className='bg-background text-muted-foreground px-2'>
            {OAUTH_DIVIDER_TEXT}
          </span>
        </div>
      </div>
      <div className='flex flex-col gap-2'>
        {providers.map((provider) => (
          <Button
            key={provider.slug}
            variant='outline'
            type='button'
            disabled={disabled}
            onClick={() => handleClick(provider)}
            className='h-11 w-full justify-center gap-2 rounded-lg'
          >
            <ProviderIcon icon={provider.icon} />
            使用 {provider.name} 登录
          </Button>
        ))}
      </div>
    </div>
  )
}
