import { useEffect } from 'react'

import { router } from '@/app/router'

/**
 * OAuth 回调 hash 桥（12_登录与错误页.md §3.5 契约）：
 * 后端 oauth_bp.py:27-28,91 回调 302 固定回 `{base}/#/login?oauth_token=…` /
 * `#/login?oauth_error=…`（Vue hash 路由遗留契约）。React 用 browser history，
 * 本组件在应用挂载时把该 hash 片段转译为 /login 的浏览器历史 search 参数，
 * 由登录页 useOAuthCallback 消化；无 OAuth 参数时零开销不导航。
 */
export function OAuthHashCallbackBridge() {
  useEffect(() => {
    const hash = window.location.hash
    if (!hash.startsWith('#/login?')) return
    const params = new URLSearchParams(hash.slice('#/login?'.length))
    const oauthToken = params.get('oauth_token')
    const oauthError = params.get('oauth_error')
    if (!oauthToken && !oauthError) return
    const search: Record<string, string> = {}
    if (oauthToken) search.oauth_token = oauthToken
    if (oauthError) search.oauth_error = oauthError
    const redirect = params.get('redirect')
    if (redirect) search.redirect = redirect
    void router.navigate({ to: '/login', search, replace: true })
  }, [])
  return null
}
