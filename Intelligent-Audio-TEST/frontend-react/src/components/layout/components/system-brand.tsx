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
import { Link } from '@tanstack/react-router'
import { Headphones } from 'lucide-react'

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

type SystemBrandProps = {
  defaultName?: string
  defaultVersion?: string
  /**
   * 视觉版式：
   * - 'sidebar'：侧栏头部堆叠品牌卡（展示用）
   * - 'inline'：顶栏紧凑胶囊，点击回主页（/）
   */
  variant?: 'sidebar' | 'inline'
}

/**
 * 系统品牌组件（本平台适配版）：Headphones 图标 + 「智能语音测试平台」。
 * 去 newAPI 的 status/logo 远程配置依赖（红线④：品牌常量本地化）。
 */
export function SystemBrand(props: SystemBrandProps) {
  const variant = props.variant ?? 'sidebar'
  const name = props.defaultName ?? '智能语音测试平台'
  const version = props.defaultVersion ?? '演示版'

  if (variant === 'inline') {
    return (
      <Link
        to='/'
        aria-label='返回主页'
        className={cn(
          'text-foreground inline-flex h-7 min-w-0 items-center gap-1.5 rounded-md px-1.5 text-sm font-medium transition-colors outline-none select-none',
          'hover:bg-accent focus-visible:ring-ring/40 focus-visible:ring-2'
        )}
      >
        <div className='bg-primary/10 text-primary flex size-5 shrink-0 items-center justify-center rounded-md'>
          <Headphones aria-hidden='true' className='size-3.5' />
        </div>
        <span className='max-w-[12rem] truncate'>{name}</span>
      </Link>
    )
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          size='lg'
          className='hover:text-sidebar-foreground active:text-sidebar-foreground cursor-default hover:bg-transparent active:bg-transparent'
          render={<div />}
        >
          <div className='bg-primary/10 text-primary flex aspect-square size-8 items-center justify-center rounded-lg'>
            <Headphones aria-hidden='true' className='size-4' />
          </div>
          <div className='grid flex-1 text-start text-sm leading-tight group-data-[collapsible=icon]:hidden'>
            <span className='truncate font-semibold'>{name}</span>
            <span className='text-muted-foreground truncate text-xs'>
              {version}
            </span>
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
