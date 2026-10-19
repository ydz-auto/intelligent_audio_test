import { Link, useNavigate } from '@tanstack/react-router'

import { ConfigDrawer } from '@/components/config-drawer'
import { NotificationPopover } from '@/components/notification-popover'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { useNotifications } from '@/application/hooks/use-notifications'
import { useTopNavLinks } from '@/application/hooks/use-top-nav-links'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { SystemBrand } from '@/components/layout/components/system-brand'
import { TopNav } from '@/components/layout/components/top-nav'
import { cn } from '@/lib/utils'

/**
 * 公开页站头（页本级最小壳，03_首页.md §3.1 消费侧）。
 * TODO(导航栏卡 INT-344): 滚动胶囊/移动端蒙层菜单/需要登录对话框/受限项过滤
 * 随公共外壳统一定稿后合并替换——本件仅承载门户页可视稿的站头装配。
 */
export function PublicHeader({ className }: { className?: string }) {
  const links = useTopNavLinks()
  const notifications = useNotifications()
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()

  return (
    <header
      className={cn(
        'bg-background/80 sticky top-0 z-40 w-full border-b backdrop-blur',
        className
      )}
    >
      <div className='mx-auto flex h-14 w-full max-w-6xl items-center gap-2 px-6 sm:px-10'>
        <SystemBrand variant='inline' />
        <div className='ms-2 hidden min-w-0 flex-1 items-center md:flex'>
          <TopNav links={links} />
        </div>
        <div className='ms-auto flex shrink-0 items-center gap-1 sm:gap-2'>
          {user ? (
            <Button size='sm' render={<Link to='/dashboard' />}>
              进入工作台
            </Button>
          ) : (
            <Button size='sm' onClick={() => void navigate({ to: '/login' })}>
              登录
            </Button>
          )}
          <NotificationPopover
            open={notifications.popoverOpen}
            onOpenChange={notifications.setPopoverOpen}
            unreadCount={notifications.unreadCount}
            activeTab={notifications.activeTab}
            onTabChange={notifications.setActiveTab}
            notice={notifications.notice}
            announcements={notifications.announcements}
            loading={notifications.loading}
            onMarkAllRead={notifications.markAllRead}
          />
          <ConfigDrawer />
        </div>
      </div>
    </header>
  )
}

/** 页脚（03_首页.md §6 页脚文案；品牌列 + 版权行） */
export function PublicFooter({ className }: { className?: string }) {
  return (
    <footer className={cn('border-border/40 border-t', className)}>
      <div className='mx-auto w-full max-w-6xl px-6 py-12 md:py-16'>
        <div className='flex flex-col gap-6 md:flex-row md:items-start md:justify-between'>
          <div className='max-w-md'>
            <SystemBrand variant='inline' />
            <p className='text-muted-foreground mt-3 text-sm leading-7'>
              面向语音团队的端到端测试与 API 测试平台。
            </p>
          </div>
          <div className='text-muted-foreground flex flex-wrap items-center gap-x-5 gap-y-2 text-sm'>
            <Link
              to='/login'
              className='hover:text-foreground transition-colors'
            >
              登录
            </Link>
            <Separator orientation='vertical' className='hidden h-4 sm:block' />
            <span>文档</span>
            <Separator orientation='vertical' className='hidden h-4 sm:block' />
            <span>关于</span>
          </div>
        </div>
        <div className='border-border/60 mt-10 border-t pt-6'>
          <p className='text-muted-foreground text-xs'>
            © {new Date().getFullYear()} 智能语音测试平台. 保留所有权利。
          </p>
        </div>
      </div>
    </footer>
  )
}
