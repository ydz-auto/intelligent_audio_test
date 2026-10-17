/**
 * OAuth 回调消化（application 层，12_登录与错误页.md §3.5/§9）：
 * 服务端 302 回 /login?oauth_token=… / oauth_error=…（oauth_bp.py:27-28,91
 * 契约）→ 成功 loginWithToken（拉 /auth/me 落 store）+ sanitize 回跳 +
 * toast「登录成功」；失败 toast「OAuth 登录失败：{error}」。URL 参数用后即清
 * （replace 导航，token 不留地址栏历史）。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { sanitizeAuthRedirect } from '@/domain/lib/auth-redirect'

export function useOAuthCallback(params: {
  oauthToken?: string
  oauthError?: string
  redirectTo?: string
}) {
  const navigate = useNavigate()
  /** OAuth 处理中整卡加载态（§3.5：呈现期间防表单闪烁） */
  const [processing, setProcessing] = useState(Boolean(params.oauthToken))
  const ranRef = useRef(false)

  useEffect(() => {
    if (ranRef.current) return
    ranRef.current = true
    void (async () => {
      if (params.oauthError) {
        toast.error(`OAuth 登录失败：${params.oauthError}`)
        await navigate({ to: '/login', search: {}, replace: true })
        return
      }
      if (!params.oauthToken) return
      try {
        await useAuthStore.getState().loginWithToken(params.oauthToken)
        toast.success('登录成功')
        const target = params.redirectTo
          ? (sanitizeAuthRedirect(params.redirectTo, window.location.origin) ??
            '/dashboard')
          : '/dashboard'
        await navigate({ to: target, replace: true })
      } catch {
        // token 无效/过期：client 侧已清登录态；提示后停留登录页重试
        toast.error('OAuth 登录失败，请重试')
        setProcessing(false)
      }
    })()
  }, [params.oauthToken, params.oauthError, params.redirectTo, navigate])

  return { processing }
}
