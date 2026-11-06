/**
 * 用户身份卡 + 个人数据快捷条（13_个人中心.md §3.2/§3.3）：
 * 对位 newAPI profile-header.tsx 版式——头像（用户名哈希取色）+ 用户名/角色/用户 ID
 * 徽章行 + @username 次行；底部快捷条三格（我的收藏/我的任务/我的报告），
 * 收藏格弹 Popover 明细，任务/报告格深链列表页。加载态照 profile-header 骨架。
 */
import { Link } from '@tanstack/react-router'
import {
  ChevronRight,
  ClipboardList,
  FileBarChart,
  Heart,
  ListChecks,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { useFavorites } from '@/application/profile/use-favorites'
import {
  canSeeFavoriteReports,
  canSeeFavoriteTasks,
  canSeeFavoriteTestcases,
  canSeeMyReports,
  canSeeMyTasks,
  type PermissionUser,
} from '@/application/profile/permission-gate'
import { useCurrentUser } from '@/application/profile/use-current-user'
import { CopyButton } from '@/components/copy-button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { IconBadge } from '@/components/ui/icon-badge'
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { getUserAvatarFallback, getUserAvatarStyle } from '@/lib/avatar'
import { cn } from '@/lib/utils'

import {
  COPY_USER_ID_ARIA,
  COPY_USER_ID_TOAST,
  FAVORITES_EMPTY_DESCRIPTION,
  FAVORITES_EMPTY_TITLE,
  FAVORITES_POPOVER_TITLE,
  FAVORITE_ROW_LABELS,
  PROFILE_LOADING_ARIA,
  QUICK_STAT_DESCRIPTIONS,
  QUICK_STAT_LABELS,
  QUICK_STAT_PENDING_VALUE,
} from '../constants'

/** 快捷条格单元（新API 额度统计条版式，§1.2/§3.3） */
function QuickStatCell({
  icon,
  tone,
  label,
  value,
  description,
  mutedValue = false,
  className,
}: {
  icon: ReactNode
  tone: 'success' | 'info' | 'chart-4'
  label: string
  value: ReactNode
  description: string
  mutedValue?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        'px-3 py-3 text-start sm:px-5 sm:py-4',
        className
      )}
    >
      <div className='flex items-center gap-2'>
        <IconBadge tone={tone} size='stat' decorative>
          {icon}
        </IconBadge>
        <span className='text-muted-foreground text-xs font-medium tracking-wider uppercase'>
          {label}
        </span>
      </div>
      <div
        className={cn(
          'font-mono text-lg font-bold tabular-nums sm:text-2xl',
          mutedValue && 'text-muted-foreground'
        )}
      >
        {value}
      </div>
      <div className='text-muted-foreground/60 hidden text-xs md:block'>
        {description}
      </div>
    </div>
  )
}

type FavoriteRow = {
  key: 'task' | 'report' | 'testcase'
  icon: LucideIcon
  count: number
  visible: boolean
}

const FAVORITE_ROW_CLASS =
  'hover:bg-muted flex items-center gap-2.5 rounded-md px-2 py-2 transition-colors'

/** 我的收藏明细 Popover（§3.3.1）：三行按实体 read 权限码过滤，计数 0 可点进空列表 */
function FavoritesPopover({
  user,
  isLoading,
}: {
  user: PermissionUser
  isLoading: boolean
}) {
  const { counts, total } = useFavorites()

  const allRows: FavoriteRow[] = [
    {
      key: 'task',
      icon: ClipboardList,
      count: counts.task,
      visible: canSeeFavoriteTasks(user),
    },
    {
      key: 'report',
      icon: FileBarChart,
      count: counts.report,
      visible: canSeeFavoriteReports(user),
    },
    {
      key: 'testcase',
      icon: ListChecks,
      count: counts.testcase,
      visible: canSeeFavoriteTestcases(user),
    },
  ]
  const rows = allRows.filter((row) => row.visible)

  return (
    <Popover>
      <PopoverTrigger
        render={
          <button
            type='button'
            aria-label={QUICK_STAT_LABELS.favorites}
            className='cursor-pointer transition-colors hover:text-primary'
          />
        }
      >
        <QuickStatCell
          icon={<Heart aria-hidden='true' />}
          tone='chart-4'
          label={QUICK_STAT_LABELS.favorites}
          value={isLoading ? '…' : total}
          description={QUICK_STAT_DESCRIPTIONS.favorites}
        />
      </PopoverTrigger>
      <PopoverContent className='w-64'>
        <PopoverHeader>
          <PopoverTitle>{FAVORITES_POPOVER_TITLE}</PopoverTitle>
        </PopoverHeader>
        {rows.length === 0 ? (
          <div className='px-1 pb-1'>
            <p className='text-sm font-medium'>{FAVORITES_EMPTY_TITLE}</p>
            <p className='text-muted-foreground text-xs'>
              {FAVORITES_EMPTY_DESCRIPTION}
            </p>
          </div>
        ) : (
          <div className='grid gap-0.5'>
            {rows.map((row) => {
              const RowIcon = row.icon
              const inner = (
                <>
                  <RowIcon
                    aria-hidden='true'
                    className='text-muted-foreground size-4 shrink-0'
                  />
                  <span className='min-w-0 flex-1 truncate text-sm'>
                    {FAVORITE_ROW_LABELS[row.key]}
                  </span>
                  <span
                    className={cn(
                      'font-mono text-sm font-bold tabular-nums',
                      row.count === 0 && 'text-muted-foreground'
                    )}
                  >
                    {row.count}
                  </span>
                  <ChevronRight
                    aria-hidden='true'
                    className='text-muted-foreground size-3.5 shrink-0'
                  />
                </>
              )
              if (row.key === 'task') {
                return (
                  <Link
                    key={row.key}
                    to='/tasks/$tab'
                    params={{ tab: 'daily' }}
                    search={{ favorite: true }}
                    className={FAVORITE_ROW_CLASS}
                  >
                    {inner}
                  </Link>
                )
              }
              if (row.key === 'report') {
                return (
                  <Link
                    key={row.key}
                    to='/report-center'
                    search={{ favorite: 'true' }}
                    className={FAVORITE_ROW_CLASS}
                  >
                    {inner}
                  </Link>
                )
              }
              return (
                <Link
                  key={row.key}
                  to='/testcases/$view'
                  params={{ view: 'by-group' }}
                  search={{ favorite: true }}
                  className={FAVORITE_ROW_CLASS}
                >
                  {inner}
                </Link>
              )
            })}
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}

/** 身份卡加载态骨架（照 profile-header.tsx：头像 + 三行 + 快捷条三格） */
function ProfileHeaderSkeleton() {
  return (
    <Card className='gap-0 overflow-hidden py-0'>
      <div
        className='flex items-center gap-3 px-4 py-4 sm:px-6 sm:py-5'
        aria-label={PROFILE_LOADING_ARIA}
      >
        <Skeleton className='size-12 rounded-xl sm:size-16 sm:rounded-2xl' />
        <div className='grid flex-1 gap-2'>
          <Skeleton className='h-6 w-40 sm:h-7' />
          <Skeleton className='h-4 w-56' />
        </div>
      </div>
      <div className='grid grid-cols-3 divide-x border-t'>
        {[0, 1, 2].map((index) => (
          <div key={index} className='px-3 py-4 sm:px-5'>
            <Skeleton className='mb-2 h-4 w-20' />
            <Skeleton className='h-6 w-14 sm:h-7' />
          </div>
        ))}
      </div>
    </Card>
  )
}

export function ProfileHeader() {
  const { user } = useCurrentUser()
  const { isLoading } = useFavorites()

  if (!user || isLoading) {
    return <ProfileHeaderSkeleton />
  }

  const showMyTasks = canSeeMyTasks(user)
  const showMyReports = canSeeMyReports(user)

  return (
    <Card className='gap-0 overflow-hidden py-0'>
      {/* 身份行（§3.2） */}
      <div className='flex items-center gap-3 px-4 py-4 sm:px-6 sm:py-5'>
        <Avatar className='size-12 shrink-0 rounded-xl ring-2 ring-background sm:size-16 sm:rounded-2xl sm:ring-4'>
          <AvatarFallback
            style={getUserAvatarStyle(user.username)}
            className='text-lg font-semibold text-white sm:text-xl'
          >
            {getUserAvatarFallback(user.username)}
          </AvatarFallback>
        </Avatar>
        <div className='grid min-w-0 flex-1 gap-1'>
          <div className='flex min-w-0 flex-wrap items-center gap-2'>
            <h2 className='min-w-0 truncate text-xl font-semibold tracking-tight sm:text-2xl'>
              {user.username}
            </h2>
            {user.roleName && (
              <Badge className='bg-muted text-muted-foreground'>
                {user.roleName}
              </Badge>
            )}
            <Badge className='bg-info/10 text-info'>
              <span className='min-w-0 truncate'>用户 ID {user.id}</span>
              <CopyButton
                value={user.id}
                aria-label={COPY_USER_ID_ARIA}
                successTooltip={COPY_USER_ID_TOAST}
                className='-me-1 -ms-1 size-4 [&_svg]:size-3'
                iconClassName='size-3'
              />
            </Badge>
          </div>
          <p className='text-muted-foreground min-w-0 truncate text-xs sm:text-sm'>
            @{user.username}
          </p>
        </div>
      </div>

      {/* 个人数据快捷条（§3.3；整格可点，hover 浮起 text-primary） */}
      <div className='grid grid-cols-3 divide-x border-t'>
        <FavoritesPopover user={user} isLoading={isLoading} />
        {showMyTasks && (
          <Link
            to='/tasks/$tab'
            params={{ tab: 'daily' }}
            className='cursor-pointer transition-colors hover:text-primary'
          >
            <QuickStatCell
              icon={<ClipboardList aria-hidden='true' />}
              tone='info'
              label={QUICK_STAT_LABELS.tasks}
              value={QUICK_STAT_PENDING_VALUE}
              description={QUICK_STAT_DESCRIPTIONS.tasks}
              mutedValue
            />
          </Link>
        )}
        {showMyReports && (
          <Link
            to='/reports'
            className='cursor-pointer transition-colors hover:text-primary'
          >
            <QuickStatCell
              icon={<FileBarChart aria-hidden='true' />}
              tone='success'
              label={QUICK_STAT_LABELS.reports}
              value={QUICK_STAT_PENDING_VALUE}
              description={QUICK_STAT_DESCRIPTIONS.reports}
              mutedValue
            />
          </Link>
        )}
      </div>
    </Card>
  )
}
