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
import { ConfigDrawer } from '@/components/config-drawer'
import { LanguageSwitcher } from '@/components/language-switcher'
import { NotificationPopover } from '@/components/notification-popover'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { useNotifications } from '@/application/hooks/use-notifications'
import { useTopNavLinks } from '@/application/hooks/use-top-nav-links'

import { AgentWorkbenchButton } from './agent-workbench-button'
import { GlobalAlgorithmSwitcher } from './global-algorithm-switcher'
import { Header } from './header'
import { SystemBrand } from './system-brand'
import { TopNav } from './top-nav'

/**
 * 通用应用头部（本平台适配版）。
 * 右区顺序（02_导航栏.md 定稿 + INT-598 增项）：Agent 工作台魔法按钮 → 算法切换器 → 搜索 → 通知 → 语言 → 主题 → 头像。
 * 去 newAPI 的签到/钱包充值/系统更新项；顶部导航项本体归导航栏卡 INT-344。
 */
type AppHeaderProps = {
  showTopNav?: boolean
  leftContent?: React.ReactNode
  showSearch?: boolean
  rightContent?: React.ReactNode
  showNotifications?: boolean
  showConfigDrawer?: boolean
  showProfileDropdown?: boolean
  /** 右区全局算法切换器显隐（INT-344 §3.4 契约；报告展示页 /reports 置 false，INT-442） */
  showGlobalAlgorithmSwitcher?: boolean
}

export function AppHeader({
  showTopNav = true,
  leftContent,
  showSearch = true,
  rightContent,
  showNotifications = true,
  showConfigDrawer = true,
  showProfileDropdown = true,
  showGlobalAlgorithmSwitcher = true,
}: AppHeaderProps) {
  const links = useTopNavLinks()
  const notifications = useNotifications()

  return (
    <Header
      className='h-auto min-h-[var(--app-header-height,3rem)]'
      contentClassName='flex-wrap py-1.5 lg:flex-nowrap lg:py-0'
    >
      <div className='@container/system-brand flex min-w-0 flex-1 items-center gap-1 lg:w-60 lg:flex-none'>
        <SystemBrand variant='inline' />
      </div>

      {leftContent ? (
        <div className='ms-2 flex min-w-0 flex-1 items-center'>
          {leftContent}
        </div>
      ) : (
        showTopNav &&
        links.length > 0 && (
          <div className='ms-auto flex min-w-0 shrink-0 items-center lg:ms-2 lg:flex-1'>
            <TopNav links={links} />
          </div>
        )
      )}

      {rightContent ?? (
        <div className='ms-auto flex max-w-full shrink-0 basis-full items-center justify-end gap-1 sm:gap-2 lg:basis-auto'>
          {/* 全局 Agent 工作台魔法按钮（INT-598 §3.1B；INT-344 右区装配，落位置于全局算法切换器之前） */}
          <AgentWorkbenchButton />
          {showGlobalAlgorithmSwitcher && <GlobalAlgorithmSwitcher />}
          {showSearch && (
            <Search className='!w-8 !flex-none !px-0 sm:!w-8 sm:!pe-0 lg:!w-8 xl:!w-8 2xl:!w-40 2xl:!pe-12 [&>kbd]:hidden 2xl:[&>kbd]:flex [&>span]:hidden 2xl:[&>span]:inline' />
          )}
          {showNotifications && (
            <NotificationPopover
              open={notifications.popoverOpen}
              onOpenChange={notifications.setPopoverOpen}
              unreadCount={notifications.unreadCount}
              activeTab={notifications.activeTab}
              onTabChange={notifications.setActiveTab}
              notice={notifications.notice}
              announcements={notifications.announcements}
              loading={notifications.loading}
            />
          )}
          <LanguageSwitcher />
          {showConfigDrawer && <ConfigDrawer />}
          {showProfileDropdown && <ProfileDropdown />}
        </div>
      )}
    </Header>
  )
}
