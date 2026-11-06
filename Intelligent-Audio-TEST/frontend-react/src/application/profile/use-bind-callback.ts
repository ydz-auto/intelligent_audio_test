/**
 * OAuth 绑定回调处理 hook（application 层，13_个人中心.md §3.5.2/§7）：
 * 页面 onMount 消化 bind_ticket / bind_error（照 AccountSettings.vue:150-165），
 * 处理后 router.replace 清 query，避免刷新重复提交。
 * 回调链路：绑定授权 → intent=bind 回调 302 → #/AccountSettings?bind_ticket=… →
 * 旧链 redirect 保留 query → /profile?bind_ticket=… → 本 hook 携票落库。
 */
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'

import { completeOAuthBinding } from '@/infrastructure/api/profileApi'

type BindCallbackSearch = {
  bind_ticket?: string
  bind_error?: string
}

export function useBindCallback() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as BindCallbackSearch
  /** 防重复处理（同一票据只消化一次，避免 StrictMode 双执行/刷新重提） */
  const handledTicket = useRef<string | null>(null)

  useEffect(() => {
    const ticket = search.bind_ticket
    const bindError = search.bind_error

    if (bindError) {
      toast.error(`绑定失败：${bindError}`)
      void navigate({ to: '/profile', search: {} })
      return
    }

    if (ticket && handledTicket.current !== ticket) {
      handledTicket.current = ticket
      void completeOAuthBinding(ticket)
        .then(() => toast.success('绑定成功'))
        .catch((error: unknown) =>
          toast.error(
            `绑定失败：${error instanceof Error ? error.message : '未知原因'}`
          )
        )
        .finally(() => {
          void navigate({ to: '/profile', search: {} })
        })
    }
  }, [search.bind_ticket, search.bind_error, navigate])
}
