/**
 * 带图标标题卡（features/profile 页级包装，对位 newAPI web/src/components/ui/titled-card.tsx）：
 * IconBadge + 标题 + 描述 + 内容区。基座卡 27 基元清单内的 TitledCard 尚未落地
 * （components/ui 仅基座 agent 写，红线②），本页先以 Card 组合等价呈现；
 * 基座落地后替换为共享件（页面卡不重复实现通用件）。
 */
import type { ReactNode } from 'react'

import { IconBadge, type IconBadgeTone } from '@/components/ui/icon-badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type TitledCardProps = {
  icon?: ReactNode
  tone?: IconBadgeTone
  title: string
  description?: string
  className?: string
  children?: ReactNode
}

export function TitledCard(props: TitledCardProps) {
  return (
    <Card
      size='sm'
      className={cn('gap-0 overflow-hidden py-0', props.className)}
    >
      <CardHeader className='px-3 pb-2 pt-3 sm:px-4 sm:pt-4'>
        <div className='flex items-center gap-2.5'>
          {props.icon && (
            <IconBadge tone={props.tone} size='sm' decorative>
              {props.icon}
            </IconBadge>
          )}
          <div className='grid gap-0.5'>
            <CardTitle className='text-sm'>{props.title}</CardTitle>
            {props.description && (
              <CardDescription className='text-xs sm:text-sm'>
                {props.description}
              </CardDescription>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className='px-3 pb-3 pt-2 sm:px-4 sm:pb-4'>
        {props.children}
      </CardContent>
    </Card>
  )
}
