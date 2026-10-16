import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { useEffect } from 'react'

/**
 * /AccountSettings 旧链 redirect → /profile（13_个人中心.md §2.1/§3.5.2）：
 * 原账号设置页并入个人中心；redirect **保留 query**（bind_ticket/bind_error）——
 * 供 OAuth 绑定回调（_FRONTEND_BIND_REDIRECT 现指向 #/AccountSettings，oauth_bp.py:30）
 * 302 回落后携票转入 /profile，页面 onMount 消化后清参。
 * 00 总表 §2.2 行 167 旧链清单；无权限码 meta（登录即可，登录壳守卫兜底）。
 * 用组件内 navigate（replace）而非 beforeLoad redirect：redirect 在首屏 URL 落地时
 * 会丢 search（INT-513 实测），组件内 replace 能完整保留 query。
 */
type AccountSettingsSearch = {
  bind_ticket?: string
  bind_error?: string
}

export const Route = createFileRoute('/_authenticated/AccountSettings')({
  component: AccountSettingsRedirect,
})

function AccountSettingsRedirect() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as AccountSettingsSearch

  useEffect(() => {
    void navigate({
      to: '/profile',
      replace: true,
      search: {
        bind_ticket: search.bind_ticket,
        bind_error: search.bind_error,
      },
    })
  }, [search.bind_ticket, search.bind_error, navigate])

  return null
}
