import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'

import { router } from '@/app/router'
import { OAuthHashCallbackBridge } from '@/features/auth/lib/oauth-hash-bridge'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
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
  // 应用启动会话恢复：token 存在时 GET /auth/me 回填 user（persist 对齐；
  // 401 由 client 侧会话过期清理，后端未起时保留本地登录态）
  useEffect(() => {
    void useAuthStore.getState().hydrateSession()
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
