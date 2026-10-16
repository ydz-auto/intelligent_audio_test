/**
 * 右列快捷入口卡 + 外观提示（13_个人中心.md §3.6/§3.6.1）：
 * 对位 newAPI 右列 sticky 卡形态——整行 Link + IconBadge + 名称/描述 + ChevronRight；
 * 「系统设置」行按设置域权限隐藏（§4.2）；底部 Alert 提示主题外观调整入口（零特判）。
 */
import { Link } from '@tanstack/react-router'
import {
  BookOpen,
  ChevronRight,
  Info,
  LayoutDashboard,
  Palette,
  Settings,
  type LucideIcon,
} from 'lucide-react'

import {
  canSeeSettingsQuickLink,
  type PermissionUser,
} from '@/application/profile/permission-gate'
import { useCurrentUser } from '@/application/profile/use-current-user'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { IconBadge, type IconBadgeTone } from '@/components/ui/icon-badge'
import { cn } from '@/lib/utils'

import {
  APPEARANCE_ALERT_DESCRIPTION,
  APPEARANCE_ALERT_TITLE,
  QUICK_LINK_COPY,
  QUICK_LINKS_TITLE,
} from '../constants'
import { TitledCard } from './titled-card'

type QuickLinkRow = {
  key: keyof typeof QUICK_LINK_COPY
  icon: LucideIcon
  tone: IconBadgeTone
  to: string
  params?: Record<string, string>
  visible: (user: PermissionUser) => boolean
}

const QUICK_LINKS: QuickLinkRow[] = [
  {
    key: 'dashboard',
    icon: LayoutDashboard,
    tone: 'neutral',
    to: '/dashboard',
    visible: () => true,
  },
  {
    key: 'settings',
    icon: Settings,
    tone: 'neutral',
    to: '/system-settings/$domain/$section',
    params: { domain: 'site', section: 'info' },
    visible: canSeeSettingsQuickLink,
  },
  {
    key: 'guide',
    icon: BookOpen,
    tone: 'neutral',
    to: '/user-guide',
    visible: () => true,
  },
  {
    key: 'about',
    icon: Info,
    tone: 'neutral',
    to: '/about',
    visible: () => true,
  },
]

function QuickLinkItem({
  row,
  className,
}: {
  row: QuickLinkRow
  className?: string
}) {
  const Icon = row.icon
  const copy = QUICK_LINK_COPY[row.key]
  return (
    <Link
      to={row.to}
      params={row.params}
      className={cn(
        'hover:bg-muted flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors',
        className
      )}
    >
      <IconBadge tone={row.tone} size='sm' decorative>
        <Icon aria-hidden='true' />
      </IconBadge>
      <span className='min-w-0 flex-1'>
        <span className='block text-sm font-medium'>{copy.label}</span>
        <span className='text-muted-foreground block truncate text-xs'>
          {copy.description}
        </span>
      </span>
      <ChevronRight
        aria-hidden='true'
        className='text-muted-foreground size-3.5 shrink-0'
      />
    </Link>
  )
}

export function QuickLinksCard() {
  const { user } = useCurrentUser()

  return (
    <TitledCard
      title={QUICK_LINKS_TITLE}
      className='gap-1'
    >
      <div className='grid gap-0.5'>
        {QUICK_LINKS.filter((row) => row.visible(user)).map((row) => (
          <QuickLinkItem key={row.key} row={row} />
        ))}
      </div>
      <Alert className='mt-1'>
        <Palette aria-hidden='true' />
        <AlertTitle className='text-xs'>{APPEARANCE_ALERT_TITLE}</AlertTitle>
        <AlertDescription className='text-xs'>
          {APPEARANCE_ALERT_DESCRIPTION}
        </AlertDescription>
      </Alert>
    </TitledCard>
  )
}
