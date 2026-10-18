import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'

import { router } from '@/app/router'
import { OAuthHashCallbackBridge } from '@/features/auth/lib/oauth-hash-bridge'
import { ensureAuthSession } from '@/infrastructure/stores/auth-store'
import { ensureSiteConfig } from '@/infrastructure/stores/site-config-store'
import { Toaster } from '@/components/ui/sonner'
import { ThemeCustomizationProvider } from '@/context/theme-customization-provider'
import { ThemeProvider } from '@/context/theme-provider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

/**
 * 全局 Provider 编排（DDD src/app 层）：
 * ThemeProvider（深浅色）→ ThemeCustomizationProvider（预设/字体/圆角/密度/内容宽度）
 * → QueryClientProvider → RouterProvider；sonner Toaster 跟随主题。
 */
export function Providers() {
  // 应用启动会话恢复（守卫共享同一引导 promise，避免重复请求）：
  // 有 token → GET /auth/me 回填 user；AUTH_MODE=off → dev_user 放行
  // （12_登录与错误页.md §3.1）；401 由 client 侧会话过期清理。
  // 站点配置并行引导（壳 INT-607）：systemName 真实端点失败回落缺省值。
  useEffect(() => {
    void ensureAuthSession()
    void ensureSiteConfig()
  }, [])

  return (
    <ThemeProvider>
      <ThemeCustomizationProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <OAuthHashCallbackBridge />
          <Toaster />
        </QueryClientProvider>
      </ThemeCustomizationProvider>
    </ThemeProvider>
  )
}
