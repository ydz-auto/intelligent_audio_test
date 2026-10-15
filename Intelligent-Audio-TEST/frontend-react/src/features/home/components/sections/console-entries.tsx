import { Link } from '@tanstack/react-router'
import { ArrowUpRight } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from '@/components/ui/card'
import { usePermissions } from '@/application/hooks/use-permissions'
import { cn } from '@/lib/utils'

import { CONSOLE_ENTRIES } from '../../constants'

/**
 * ④ 控制台功能入口（03_首页.md §3.5）：八张四色卡 + RBAC 权限过滤。
 * 未登录/无任何可显卡 → 整区替换为引导行（RBAC 未登录降级文案）；
 * 有权限卡时逐卡渲染（mock 管理员 '*' 全显）。
 */
export function ConsoleEntriesSection({ className }: { className?: string }) {
  const { hasPermission } = usePermissions()
  const visibleCards = CONSOLE_ENTRIES.cards.filter((card) =>
    hasPermission(card.permission)
  )

  return (
    <section
      id='console-entries'
      aria-labelledby='home-entries-heading'
      className={cn(className, 'scroll-mt-24 px-6 py-16 sm:px-10 lg:py-24')}
    >
      <div className='mx-auto max-w-6xl'>
        <AnimateInView>
          <div className='mb-10 grid gap-5 md:grid-cols-[1fr_auto] md:items-end'>
            <div>
              <p className='text-muted-foreground mb-4 font-mono text-xs tracking-widest'>
                {CONSOLE_ENTRIES.eyebrow}
              </p>
              <h2
                id='home-entries-heading'
                className='max-w-2xl text-3xl leading-tight font-medium tracking-tight sm:text-4xl'
              >
                {CONSOLE_ENTRIES.heading}
              </h2>
            </div>
            <Button
              variant='link'
              className='h-auto justify-start p-0'
              render={<Link to='/dashboard' />}
            >
              {CONSOLE_ENTRIES.consoleLink}
              <ArrowUpRight aria-hidden='true' className='size-4' />
            </Button>
          </div>
        </AnimateInView>

        {visibleCards.length === 0 ? (
          <p className='text-muted-foreground rounded-2xl border border-dashed px-6 py-10 text-center text-sm'>
            {CONSOLE_ENTRIES.emptyText}
          </p>
        ) : (
          <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
            {visibleCards.map((card, i) => (
              <AnimateInView key={card.key} delay={i * 50} className='min-w-0'>
                <Card className={cn('gap-0 rounded-2xl py-0 ring-0', card.color)}>
                  <CardHeader className='px-6 pt-7 pb-10'>
                    <card.icon
                      aria-hidden='true'
                      strokeWidth={1.4}
                      className='size-10'
                    />
                  </CardHeader>
                  <CardContent className='px-6 pb-7'>
                    <h3 className='text-2xl font-semibold tracking-tight'>
                      {card.name}
                    </h3>
                    <p className='mt-3 min-h-12 text-sm leading-6'>
                      {card.summary}
                    </p>
                  </CardContent>
                  <CardFooter className='border-current/15 bg-transparent! border-t px-6 py-4'>
                    <Button
                      variant='link'
                      className='h-auto w-full justify-between p-0 text-inherit'
                      render={<Link to={card.to} />}
                      aria-label={`${card.name} · 进入`}
                    >
                      进入
                      <ArrowUpRight aria-hidden='true' className='size-5' />
                    </Button>
                  </CardFooter>
                </Card>
              </AnimateInView>
            ))}
          </div>
        )}

        <p className='text-muted-foreground mt-5 text-xs leading-6'>
          {CONSOLE_ENTRIES.footnote}
        </p>
      </div>
    </section>
  )
}
