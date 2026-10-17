/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
import { useLocation } from '@tanstack/react-router'
import { AnimatedOutlet } from '@/components/page-transition'
import { SkipToMain } from '@/components/skip-to-main'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { LayoutProvider } from '@/context/layout-provider'
import { SearchProvider } from '@/context/search-provider'
import { getCookie } from '@/lib/cookies'
import { cn } from '@/lib/utils'

import { AppHeader } from './app-header'
import { AppSidebar } from './app-sidebar'
import { AgentWorkbench } from '@/features/agent-workbench/agent-workbench'

type AuthenticatedLayoutProps = {
  children?: React.ReactNode
}

export function AuthenticatedLayout(props: AuthenticatedLayoutProps) {
  const defaultOpen = getCookie('iatp:sidebar:v1:state') !== 'false'
  const location = useLocation()
  // INT-442/486 跨卡契约（00 总表 §3.5 矩阵）：/reports、/rankings 算法切换唯一入口=页内算法大卡，隐藏右上角全局切换器
  const showGlobalAlgorithmSwitcher =
    location.pathname !== '/reports' && location.pathname !== '/rankings'

  return (
    <LayoutProvider>
      <SearchProvider>
        <SidebarProvider
          defaultOpen={defaultOpen}
          className='flex-col [--app-header-height:5.5rem] lg:[--app-header-height:3rem]'
        >
          <SkipToMain />
          <AppHeader showGlobalAlgorithmSwitcher={showGlobalAlgorithmSwitcher} />
          <div className='flex min-h-0 w-full flex-1'>
            <AppSidebar />
            <SidebarInset
              className={cn(
                '@container/content',
                'h-[calc(100svh-var(--app-header-height,0px))]',
                'min-h-0 overflow-hidden',
                'peer-data-[variant=inset]:h-[calc(100svh-var(--app-header-height,0px)-(var(--spacing)*4))]'
              )}
            >
              {props.children ?? <AnimatedOutlet />}
            </SidebarInset>
          </div>
          {/* 全局 Agent 工作台浮窗（§3.1B）：渲染在壳根部，createPortal 到 body，不随路由卸载 */}
          <AgentWorkbench />
        </SidebarProvider>
      </SearchProvider>
    </LayoutProvider>
  )
}
