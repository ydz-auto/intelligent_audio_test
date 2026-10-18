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
*/
import { Bell, Megaphone } from 'lucide-react'

import type {
  AppNotification,
  NotificationTab,
} from '@/domain/models/notification'
import { notificationDotClass } from '@/infrastructure/adapters/notificationAdapter'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

type NotificationPopoverProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  unreadCount: number
  activeTab: NotificationTab
  onTabChange: (tab: NotificationTab) => void
  notice: AppNotification[]
  announcements: AppNotification[]
  loading?: boolean
  /** 全部已读动作（INT-731 接线后真实调用已读标记 store） */
  onMarkAllRead?: () => void
}

/** 相对时间梯（02_导航栏.md §3.6 照搬 newAPI getRelativeTime 实测） */
function getRelativeTime(iso: string): string {
  if (!iso) return ''
  const time = new Date(iso).getTime()
  if (Number.isNaN(time)) return ''
  const now = Date.now()
  const diffMs = now - time
  if (diffMs < 60_000) return '刚刚'
  const diffMin = Math.floor(diffMs / 60_000)
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 7) return `${diffDay} 天前`
  const d = new Date(time)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd} ${hh}:${mi}`
}

function EmptyState({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode
  title: string
  description?: string
}) {
  return (
    <Empty className='min-h-48 border-0 p-4'>
      <EmptyHeader>
        <EmptyMedia variant='icon'>{icon}</EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </EmptyHeader>
    </Empty>
  )
}

/**
 * 通知中心（右区第三项；02_导航栏.md §3.6 对位重写）。
 * 铃铛 + 未读角标 → Popover（通知/公告页签 + 滚动列表 + 空态/加载态）。
 * 数据源：通知 = SSE 事件流；公告 = 站点公告（INT-731 已接真实接口）。
 */
export function NotificationPopover({
  open,
  onOpenChange,
  unreadCount,
  activeTab,
  onTabChange,
  notice,
  announcements,
  loading = false,
  onMarkAllRead,
}: NotificationPopoverProps) {
  const items = activeTab === 'notice' ? notice : announcements

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger
        render={
          <Button
            variant='ghost'
            size='icon'
            className='relative size-8'
            aria-label='通知'
          />
        }
      >
        <Bell aria-hidden='true' />
        {unreadCount > 0 && (
          <Badge
            variant='destructive'
            className='absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[10px] font-semibold tabular-nums'
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </Badge>
        )}
      </PopoverTrigger>
      <PopoverContent
        align='end'
        sideOffset={8}
        className='w-[min(26rem,calc(100vw-1rem))] gap-3 p-3'
      >
        <PopoverHeader className='gap-1 px-1'>
          <PopoverTitle className='flex items-center justify-between'>
            通知中心
            <Button
              variant='ghost'
              size='sm'
              className='text-muted-foreground h-7 px-2 text-xs'
              onClick={() => {
                onMarkAllRead?.()
                onOpenChange(false)
              }}
            >
              全部已读
            </Button>
          </PopoverTitle>
          <p className='text-muted-foreground text-xs'>
            任务与报告的最新动态
          </p>
        </PopoverHeader>

        <Tabs
          value={activeTab}
          onValueChange={(value) => onTabChange(value as NotificationTab)}
        >
          <TabsList className='grid w-full grid-cols-2'>
            <TabsTrigger value='notice' className='gap-1.5'>
              <Bell className='size-3.5' aria-hidden='true' />
              通知
            </TabsTrigger>
            <TabsTrigger value='announcement' className='gap-1.5'>
              <Megaphone className='size-3.5' aria-hidden='true' />
              公告
            </TabsTrigger>
          </TabsList>

          <TabsContent value={activeTab} className='mt-2'>
            {loading ? (
              <EmptyState
                icon={<Bell aria-hidden='true' />}
                title='加载中'
                description='正在获取最新通知…'
              />
            ) : items.length === 0 ? (
              <EmptyState
                icon={activeTab === 'notice' ? <Bell aria-hidden='true' /> : <Megaphone aria-hidden='true' />}
                title={activeTab === 'notice' ? '暂无通知' : '暂无公告'}
                description={
                  activeTab === 'notice'
                    ? '任务与报告的最新动态会显示在这里'
                    : '站点公告将在系统设置中配置后显示'
                }
              />
            ) : (
              <ScrollArea className='h-[min(52vh,28rem)] pr-3'>
                <div className='flex flex-col'>
                  {items.map((item, idx) => (
                    <div key={item.id}>
                      <div className='flex items-start gap-3 py-3'>
                        <span
                          aria-hidden='true'
                          className={`mt-1.5 inline-block size-2 shrink-0 rounded-full ${notificationDotClass(item.kind)}`}
                        />
                        <div className='flex min-w-0 flex-1 flex-col gap-1'>
                          <div className='flex items-center justify-between gap-2'>
                            <span className='truncate text-sm font-medium'>
                              {item.title}
                            </span>
                            {item.createdAt && (
                              <span className='text-muted-foreground shrink-0 text-xs'>
                                {getRelativeTime(item.createdAt)}
                              </span>
                            )}
                          </div>
                          <p className='text-muted-foreground line-clamp-2 text-xs'>
                            {item.content}
                          </p>
                        </div>
                      </div>
                      {idx < items.length - 1 ? <Separator /> : null}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </TabsContent>
        </Tabs>

        <div className='flex justify-end'>
          <Button size='sm' onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
