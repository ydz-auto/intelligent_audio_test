/**
 * 个人中心页（13_个人中心.md §3.1）：登录壳 _authenticated 组内页面，无页头标题栏
 * （对齐 newAPI profile 页 Main 直出身份卡）；Main + CardStaggerContainer +
 * 双列栅格（左=个人信息+账号安全，右=快捷入口 sticky）。
 * 页面进入动画照 page-transition CardStaggerContainer/CardStaggerItem（§3.1）。
 */
import { useEffect } from 'react'

import { useBindCallback } from '@/application/profile/use-bind-callback'
import { Main } from '@/components/layout/components/main'
import {
  CardStaggerContainer,
  CardStaggerItem,
} from '@/components/page-transition'

import { PROFILE_PAGE_TITLE } from './constants'
import { AccountSecurityCard } from './components/account-security-card'
import { PersonalInfoCard } from './components/personal-info-card'
import { ProfileHeader } from './components/profile-header'
import { QuickLinksCard } from './components/quick-links-card'

export function ProfilePage() {
  /** 绑定回调（bind_ticket/bind_error）onMount 消化（§3.5.2） */
  useBindCallback()

  /** 浏览器/标签标题（§3.7 路由 meta 口径；其余平台页同惯例） */
  useEffect(() => {
    document.title = PROFILE_PAGE_TITLE
  }, [])

  return (
    <Main>
      <div className='min-h-0 flex-1 overflow-y-auto px-3 py-3 sm:px-4 sm:py-6'>
        <CardStaggerContainer className='mx-auto flex w-full max-w-7xl flex-col gap-4 sm:gap-6'>
          <CardStaggerItem>
            <ProfileHeader />
          </CardStaggerItem>
          <CardStaggerItem>
            <div className='grid gap-4 sm:gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.46fr)] xl:items-start'>
              <div className='space-y-4 sm:space-y-6'>
                <PersonalInfoCard />
                <AccountSecurityCard />
              </div>
              <div className='space-y-4 sm:space-y-6 xl:sticky xl:top-6'>
                <QuickLinksCard />
              </div>
            </div>
          </CardStaggerItem>
        </CardStaggerContainer>
      </div>
    </Main>
  )
}
