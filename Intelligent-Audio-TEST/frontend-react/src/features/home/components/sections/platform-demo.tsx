import { Link } from '@tanstack/react-router'
import { Check } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { PLATFORM_DEMO } from '../../constants'
import { TerminalDemo } from '../terminal-demo'

/**
 * ⑤ 平台架构演示（03_首页.md §3.6）：左文右终端 Tabs + 尾行常用入口。
 */
export function PlatformDemoSection({ className }: { className?: string }) {
  return (
    <section
      aria-labelledby='home-demo-heading'
      className={cn(className, 'px-6 py-16 sm:px-10 lg:py-24')}
    >
      <div className='mx-auto max-w-6xl'>
        <div className='bg-muted/30 grid items-center gap-10 rounded-3xl border p-6 sm:p-10 lg:grid-cols-[0.8fr_1.2fr] lg:p-12'>
          <AnimateInView className='min-w-0'>
            <p className='text-muted-foreground mb-4 font-mono text-xs tracking-widest'>
              {PLATFORM_DEMO.eyebrow}
            </p>
            <h2
              id='home-demo-heading'
              className='text-3xl leading-tight font-medium tracking-tight sm:text-4xl'
            >
              {PLATFORM_DEMO.heading}
            </h2>
            <p className='text-muted-foreground mt-4 text-sm leading-7'>
              {PLATFORM_DEMO.description}
            </p>
            <ul className='mt-6 space-y-3'>
              {PLATFORM_DEMO.checks.map((item) => (
                <li key={item} className='flex items-center gap-2.5 text-sm'>
                  <Check
                    aria-hidden='true'
                    className='text-primary size-4'
                  />
                  {item}
                </li>
              ))}
            </ul>
            <Button
              variant='link'
              className='mt-6 h-auto p-0'
              render={<Link to='/user-guide' />}
            >
              {PLATFORM_DEMO.apiManualLink}
            </Button>
          </AnimateInView>
          <AnimateInView animation='fade-in' delay={120} className='min-w-0'>
            <TerminalDemo />
          </AnimateInView>
        </div>

        <AnimateInView>
          <div className='mt-10 grid gap-5 md:grid-cols-[1fr_auto] md:items-center'>
            <div>
              <h3 className='text-base font-semibold'>
                {PLATFORM_DEMO.commonEntries.title}
              </h3>
              <p className='text-muted-foreground mt-2 text-sm leading-7'>
                {PLATFORM_DEMO.commonEntries.description}
              </p>
            </div>
            <div className='flex flex-wrap gap-3'>
              {PLATFORM_DEMO.commonEntries.buttons.map((button) => (
                <Button
                  key={button.label}
                  variant='outline'
                  className='h-11 rounded-full px-5'
                  render={<Link to={button.to} />}
                >
                  {button.label}
                </Button>
              ))}
            </div>
          </div>
        </AnimateInView>
      </div>
    </section>
  )
}
