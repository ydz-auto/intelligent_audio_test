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
import { Bell } from 'lucide-react'

import type {
  AppNotification,
  NotificationTab,
} from '@/domain/models/notification'
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
  PopoverTrigger,
} from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

type NotificationPopoverProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  unreadCount: number
  activeTab: NotificationTab
  onTabChange: (tab: NotificationTab) => void
  notice: AppNotification[]
  announcements: AppNotification[]
  loading?: boolean
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}

/**
 * 通知中心（右区第三项；02_导航栏.md §3.6 对位重写）：
 * 铃铛 + 未读角标 → Popover（通知/公告页签 + 滚动列表 + 空态）。
 * 红线④：数据为 mock 常量；TODO(API 接线): SSE 推送 + 已读接口。
 */
export function NotificationPopover(props: NotificationPopoverProps) {
  const items =
    props.activeTab === 'notice' ? props.notice : props.announcements

  return (
    <Popover open={props.open} onOpenChange={props.onOpenChange}>
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
        {props.unreadCount > 0 && (
          <span className='bg-primary text-primary-foreground absolute -top-0.5 -end-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-medium'>
            {props.unreadCount > 99 ? '99+' : props.unreadCount}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align='end' className='w-80 p-0'>
        <div className='flex items-center justify-between px-4 py-3'>
          <span className='text-sm font-medium'>通知</span>
          <Button
            variant='ghost'
            size='sm'
            className='text-muted-foreground h-7 px-2 text-xs'
            // TODO(API 接线): 调批量已读接口
            onClick={() => props.onOpenChange(false)}
          >
            全部已读
          </Button>
        </div>
        <Separator />
        <Tabs
          value={props.activeTab}
          onValueChange={(value) => props.onTabChange(value as NotificationTab)}
        >
          <div className='px-3 pt-2'>
            <TabsList className='w-full'>
              <TabsTrigger value='notice' className='flex-1'>
                通知
              </TabsTrigger>
              <TabsTrigger value='announcement' className='flex-1'>
                公告
              </TabsTrigger>
            </TabsList>
          </div>
          <ScrollArea className='h-72'>
            {items.length === 0 ? (
              <Empty className='min-h-56 border-0'>
                <EmptyHeader>
                  <EmptyMedia variant='icon'>
                    <Bell aria-hidden='true' />
                  </EmptyMedia>
                  <EmptyTitle>
                    暂无{props.activeTab === 'notice' ? '通知' : '公告'}
                  </EmptyTitle>
                  <EmptyDescription>新消息会在这里显示</EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <ul className='divide-y'>
                {items.map((item) => (
                  <li key={item.id} className='px-4 py-3'>
                    <div className='flex items-start gap-2'>
                      {!item.read && (
                        <span
                          aria-hidden='true'
                          className='bg-primary mt-1.5 size-1.5 shrink-0 rounded-full'
                        />
                      )}
                      <div className='min-w-0 flex-1'>
                        <div className='flex items-center justify-between gap-2'>
                          <span className='truncate text-sm font-medium'>
                            {item.title}
                          </span>
                          <span className='text-muted-foreground shrink-0 text-xs'>
                            {formatTime(item.createdAt)}
                          </span>
                        </div>
                        <p className='text-muted-foreground mt-0.5 line-clamp-2 text-xs'>
                          {item.content}
                        </p>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </ScrollArea>
        </Tabs>
      </PopoverContent>
    </Popover>
  )
}
