import { createFileRoute, redirect } from '@tanstack/react-router'
import { Loader2 } from 'lucide-react'
import { z } from 'zod'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import AuthLayout from '@/features/auth/auth-layout'
import { SignIn } from '@/features/auth/sign-in'
import { useOAuthCallback } from '@/application/auth/use-oauth-callback'
import { sanitizeAuthRedirect } from '@/features/auth/lib/auth-redirect'
import { OAUTH_PROCESSING_TEXT } from '@/features/auth/constants'

const loginSearchSchema = z.object({
  redirect: z.string().optional(),
  /** 注册成功切回登录页时预填用户名（§3.6 引导流平移） */
  username: z.string().optional(),
  /** OAuth 回调携 token/错误（oauth_bp.py:27-28 契约；token 用后即清） */
  oauth_token: z.string().optional(),
  oauth_error: z.string().optional(),
})

/**
 * 登录页 /login（12_登录与错误页.md §3.1/§3.5）：
 * search 携带 redirect / username / oauth_token / oauth_error；
 * 已登录直接 sanitize 回跳，不重复渲染表单；OAuth 回调在组件内消化。
 */
export const Route = createFileRoute('/_public/login')({
  validateSearch: loginSearchSchema,
  beforeLoad: ({ search }) => {
    if (useAuthStore.getState().user) {
      const target =
        sanitizeAuthRedirect(search.redirect, window.location.origin) ??
        '/dashboard'
      throw redirect({ to: target })
    }
  },
  component: LoginPage,
})

function LoginPage() {
  const {
    redirect: redirectTo,
    username,
    oauth_token: oauthToken,
    oauth_error: oauthError,
  } = Route.useSearch()
  const { processing } = useOAuthCallback({
    oauthToken,
    oauthError,
    redirectTo,
  })

  // OAuth 回调呈现期间渲染整卡加载态（§3.5：防表单闪烁）
  if (processing) {
    return (
      <AuthLayout>
        <div className='flex flex-col items-center justify-center gap-4'>
          <Loader2 className='size-8 animate-spin' aria-hidden='true' />
          <p className='text-muted-foreground text-sm'>{OAUTH_PROCESSING_TEXT}</p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <SignIn redirectTo={redirectTo} prefillUsername={username} />
    </AuthLayout>
  )
}
