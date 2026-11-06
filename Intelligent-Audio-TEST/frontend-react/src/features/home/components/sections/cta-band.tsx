import { Link } from '@tanstack/react-router'

import { AnimateInView } from '@/components/animate-in-view'
import { Button } from '@/components/ui/button'
import { usePermissions } from '@/application/hooks/use-permissions'
import { cn } from '@/lib/utils'

import { CTA_BAND } from '../../constants'

/**
 * ⑨ 尾部 CTA（03_首页.md §3.10）：整宽主色软底色带（bg-primary/12，
 * 不写死 newAPI #c1f28b）；未登录主钮「立即体验」→ /login。
 */
export function CtaBandSection({ className }: { className?: string }) {
  const { user } = usePermissions()

  return (
    <section
      aria-labelledby='home-cta-heading'
      className={cn(
        'bg-primary/12 px-6 py-12 lg:py-16',
        className
      )}
    >
      <AnimateInView>
        <div className='mx-auto flex max-w-6xl flex-col gap-8 md:flex-row md:items-center md:justify-between'>
          <div>
            <p className='text-muted-foreground mb-4 font-mono text-xs tracking-widest'>
              {CTA_BAND.eyebrow}
            </p>
            <h2
              id='home-cta-heading'
              className='max-w-2xl text-3xl leading-tight font-medium tracking-tight sm:text-5xl'
            >
              {CTA_BAND.heading}
            </h2>
          </div>
          <div className='flex shrink-0 flex-wrap gap-3'>
            <Button
              size='lg'
              className='h-14 w-fit rounded-full px-7'
              render={<Link to={user ? '/dashboard' : '/login'} />}
            >
              {user ? CTA_BAND.primaryAction : CTA_BAND.primaryActionAnonymous}
            </Button>
            <Button
              size='lg'
              variant='outline'
              className='h-14 w-fit rounded-full px-7'
              render={<Link to='/user-guide' />}
            >
              {CTA_BAND.secondaryAction}
            </Button>
          </div>
        </div>
      </AnimateInView>
    </section>
  )
}
