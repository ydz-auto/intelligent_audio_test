import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'

import { router } from '@/app/router'
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
  return (
    <ThemeProvider>
      <ThemeCustomizationProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <Toaster />
        </QueryClientProvider>
      </ThemeCustomizationProvider>
    </ThemeProvider>
  )
}
