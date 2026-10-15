import { Link } from '@tanstack/react-router'
import { ArrowUpRight, Building2, Check, ServerCog, ShieldCheck } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePermissions } from '@/application/hooks/use-permissions'
import { cn } from '@/lib/utils'

import { DEPLOYMENT_TRUST } from '../../constants'

/**
 * ⑦ 部署与数据边界（03_首页.md §3.8）：左三条承诺 + 右系统信息卡 + 合规徽章条。
 */
export function DeploymentTrustSection({ className }: { className?: string }) {
  const { user } = usePermissions()

  return (
    <section
      aria-labelledby='home-trust-heading'
      className={cn(
        'relative isolate overflow-hidden bg-background px-6 py-16 sm:px-10 lg:py-20',
        className
      )}
    >
      <div className='mx-auto grid max-w-6xl items-start gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:gap-16'>
        <AnimateInView className='min-w-0'>
          <p className='text-primary mb-5 flex items-center gap-2 text-xs font-semibold tracking-widest'>
            <Building2 aria-hidden='true' className='size-4' />
            {DEPLOYMENT_TRUST.eyebrow}
          </p>
          <h2
            id='home-trust-heading'
            className='text-3xl leading-tight font-semibold tracking-tight text-balance sm:text-4xl'
          >
            {DEPLOYMENT_TRUST.heading}
          </h2>
          <p className='text-muted-foreground mt-5 text-base leading-8 text-pretty'>
            {DEPLOYMENT_TRUST.subtext}
          </p>
          <div className='mt-9 space-y-6'>
            {DEPLOYMENT_TRUST.commitments.map((item) => (
              <div key={item.title} className='flex gap-3'>
                <Check
                  aria-hidden='true'
                  className='text-primary mt-1 size-5 shrink-0'
                />
                <div className='min-w-0'>
                  <h3 className='text-base font-semibold'>{item.title}</h3>
                  <p className='text-muted-foreground mt-2 text-sm leading-7 text-pretty'>
                    {item.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </AnimateInView>

        <AnimateInView animation='fade-in' delay={100} className='min-w-0'>
          <div className='border-border bg-card text-card-foreground min-w-0 rounded-3xl border p-6 shadow-sm sm:p-8'>
            <div className='flex items-center justify-between gap-4'>
              <ServerCog aria-hidden='true' className='text-primary size-8' />
              <Badge variant='outline'>{DEPLOYMENT_TRUST.card.badge}</Badge>
            </div>
            <h3 className='mt-7 text-2xl font-semibold tracking-tight'>
              {DEPLOYMENT_TRUST.card.title}
            </h3>
            <p className='text-muted-foreground mt-4 text-sm leading-7'>
              {DEPLOYMENT_TRUST.card.description}
            </p>
            <dl className='mt-5'>
              {DEPLOYMENT_TRUST.card.rows.map((row) => (
                <div
                  key={row.label}
                  className='border-border/60 flex justify-between py-2 text-sm last:border-0'
                >
                  <dt>{row.label}</dt>
                  <dd className='text-muted-foreground tabular-nums'>
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>
            <Button
              size='lg'
              className='mt-6 h-auto min-h-12 w-full rounded-full px-5 py-3 whitespace-normal'
              render={<Link to={user ? '/dashboard' : '/login'} />}
            >
              {user
                ? DEPLOYMENT_TRUST.card.action
                : DEPLOYMENT_TRUST.card.manualLink}
              <ArrowUpRight aria-hidden='true' className='size-4' />
            </Button>
            {user && (
              <Link
                to='/user-guide'
                className='text-muted-foreground hover:text-foreground mt-4 block rounded-sm text-center text-xs leading-6 underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4'
              >
                {DEPLOYMENT_TRUST.card.manualLink}
              </Link>
            )}
          </div>
        </AnimateInView>
      </div>

      <AnimateInView className='mx-auto mt-10 max-w-6xl'>
        <div className='border-border bg-muted/35 flex flex-wrap items-center justify-between gap-5 rounded-2xl border px-6 py-5'>
          <div className='flex min-w-0 flex-wrap items-center gap-3'>
            <span className='flex items-center gap-2 text-sm font-semibold'>
              <ShieldCheck
                aria-hidden='true'
                className='text-primary size-5'
              />
              {DEPLOYMENT_TRUST.compliance.label}
            </span>
            {DEPLOYMENT_TRUST.compliance.badges.map((badge) => (
              <Badge
                key={badge}
                variant='outline'
                className='bg-background text-muted-foreground'
              >
                {badge}
              </Badge>
            ))}
          </div>
          <div className='flex flex-wrap gap-5'>
            {DEPLOYMENT_TRUST.compliance.links.map((label) => (
              <Button
                key={label}
                variant='link'
                className='h-auto p-0 whitespace-normal'
                render={<Link to='/user-guide' />}
              >
                {label}
              </Button>
            ))}
          </div>
        </div>
      </AnimateInView>
    </section>
  )
}
