import { Link } from '@tanstack/react-router'
import { ArrowDownRight, ArrowUpRight, Check, Sparkles } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { usePermissions } from '@/application/hooks/use-permissions'
import { cn } from '@/lib/utils'

import { HERO, HERO_BENEFITS } from '../../constants'
import { PlatformOrbit } from '../platform-orbit'
import { StatsBar } from '../stats-bar'

/**
 * ① 品牌区（03_首页.md §3.2）：左文右枢纽图 + 4 卖点卡 + 平台规模条。
 * Hero 软底 bg-muted/40（不写死 newAPI 的 #f4f6fb，多预设联动）；
 * 已登录主按钮变「进入控制台」（hero-buttons.tsx isAuthenticated 分支对位）。
 */
export function HeroSection({ className }: { className?: string }) {
  const { user } = usePermissions()

  return (
    <section
      aria-labelledby='home-hero-heading'
      className={cn(
        'bg-muted/40 relative isolate overflow-hidden px-6 pt-24 pb-8 sm:px-10 lg:pt-32',
        className
      )}
    >
      <div
        aria-hidden='true'
        className='pointer-events-none absolute top-0 right-0 -z-10 h-full w-2/3 bg-[radial-gradient(ellipse_at_75%_40%,color-mix(in_oklch,var(--primary)_10%,transparent),transparent_65%)]'
      />
      <div className='mx-auto max-w-6xl'>
        <div className='grid items-center gap-10 pb-12 lg:grid-cols-2 lg:gap-12 lg:pb-16'>
          <AnimateInView className='min-w-0'>
            <Badge
              variant='outline'
              className='border-primary/15 bg-background/70 text-primary mb-7 h-auto gap-2 rounded-full px-3 py-1.5 text-xs font-medium'
            >
              <Sparkles aria-hidden='true' className='size-3.5' />
              {HERO.badge}
            </Badge>
            <h1
              id='home-hero-heading'
              className='text-[clamp(2.25rem,4vw,3.5rem)] leading-[1.18] font-semibold tracking-tight text-balance'
            >
              {HERO.titleLine1}
              <br />
              <span className='from-primary to-secondary bg-gradient-to-r bg-clip-text text-transparent'>
                {HERO.titleLine2}
              </span>
            </h1>
            <p className='text-primary mt-5 text-lg font-semibold sm:text-xl'>
              {HERO.highlight}
            </p>
            <p className='text-muted-foreground mt-4 max-w-lg text-sm leading-7 sm:text-base sm:leading-8'>
              {HERO.description}
            </p>
            <div className='mt-6 flex flex-wrap gap-3'>
              <Button
                size='lg'
                className='h-12 rounded-full px-6'
                render={
                  <Link to={user ? '/dashboard' : '/E2ETest'} />
                }
              >
                {user ? HERO.primaryActionAuthed : HERO.primaryAction}
                <ArrowUpRight aria-hidden='true' className='size-5' />
              </Button>
              <Button
                size='lg'
                variant='outline'
                className='h-12 rounded-full px-6'
                render={<Link to='/user-guide' />}
              >
                {HERO.secondaryAction}
              </Button>
            </div>
            <div className='text-muted-foreground mt-6 flex flex-wrap gap-x-5 gap-y-2 text-xs'>
              {HERO.checks.map((label) => (
                <span key={label} className='flex items-center gap-1.5'>
                  <Check
                    aria-hidden='true'
                    className='text-primary size-3.5'
                  />
                  {label}
                </span>
              ))}
            </div>
          </AnimateInView>
          <AnimateInView
            animation='fade-in'
            delay={120}
            className='min-w-0'
          >
            <PlatformOrbit />
          </AnimateInView>
        </div>

        <ul className='mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4'>
          {HERO_BENEFITS.map((benefit, i) => (
            <AnimateInView
              as='li'
              key={benefit.title}
              delay={i * 50}
              className='min-w-0'
            >
              <Card className='bg-card/80 h-full gap-2 rounded-2xl py-5'>
                <CardHeader className='gap-3 px-5'>
                  <benefit.icon
                    aria-hidden='true'
                    className='text-primary size-5'
                  />
                  <CardTitle className='text-xl font-semibold'>
                    {benefit.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className='text-muted-foreground px-5 text-xs leading-6'>
                  {benefit.description}
                </CardContent>
              </Card>
            </AnimateInView>
          ))}
        </ul>

        <div className='mb-6'>
          <StatsBar />
        </div>

        <div className='border-border/70 flex flex-wrap items-center justify-between gap-5 border-t pt-6'>
          <div className='text-muted-foreground flex flex-wrap gap-x-6 gap-y-3 text-xs font-medium sm:text-sm'>
            {HERO.brandRow.map((name) => (
              <span key={name}>{name}</span>
            ))}
          </div>
          <a
            href='#console-entries'
            className='text-muted-foreground hover:text-foreground flex items-center gap-3 rounded-sm text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-4'
          >
            {HERO.brandRowLink}
            <ArrowDownRight aria-hidden='true' className='size-5' />
          </a>
        </div>
      </div>
    </section>
  )
}
