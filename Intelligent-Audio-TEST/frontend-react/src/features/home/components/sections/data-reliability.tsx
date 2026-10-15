import { ArrowRight } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

import { DATA_RELIABILITY } from '../../constants'

/**
 * ⑥ 数据与可靠性（03_首页.md §3.7）：三能力卡 + 全流程链路条。
 */
export function DataReliabilitySection({ className }: { className?: string }) {
  return (
    <section
      aria-labelledby='home-reliability-heading'
      className={cn(className, 'px-6 pt-16 sm:px-10 lg:pt-24')}
    >
      <div className='mx-auto max-w-6xl'>
        <AnimateInView>
          <p className='text-muted-foreground mb-4 text-xs font-semibold tracking-widest'>
            {DATA_RELIABILITY.eyebrow}
          </p>
          <h2
            id='home-reliability-heading'
            className='max-w-3xl text-3xl leading-tight font-medium tracking-tight sm:text-4xl'
          >
            {DATA_RELIABILITY.heading}
          </h2>
          <p className='text-muted-foreground mt-4 max-w-2xl text-sm leading-7'>
            {DATA_RELIABILITY.subtext}
          </p>
        </AnimateInView>
        <div className='mt-8 grid gap-4 lg:grid-cols-3'>
          {DATA_RELIABILITY.cards.map((card, i) => (
            <AnimateInView key={card.title} delay={i * 50} className='min-w-0'>
              <Card className='min-w-0 rounded-2xl py-6'>
                <CardHeader className='px-6'>
                  <CardTitle>
                    <h3 className='text-lg font-semibold'>{card.title}</h3>
                  </CardTitle>
                </CardHeader>
                <CardContent className='text-muted-foreground px-6 text-sm leading-7'>
                  {card.description}
                </CardContent>
              </Card>
            </AnimateInView>
          ))}
        </div>
        <AnimateInView delay={80}>
          <div className='border-primary/10 bg-primary/5 mt-6 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl border px-6 py-5 text-sm'>
            <span className='font-semibold'>{DATA_RELIABILITY.chainLabel}</span>
            {DATA_RELIABILITY.chain.map((node, i) => (
              <span key={node} className='flex items-center gap-3'>
                {i > 0 && (
                  <ArrowRight
                    aria-hidden='true'
                    className='text-muted-foreground size-4'
                  />
                )}
                <span>{node}</span>
              </span>
            ))}
          </div>
          <p className='text-muted-foreground mt-4 text-xs leading-6'>
            {DATA_RELIABILITY.footnote}
          </p>
        </AnimateInView>
      </div>
    </section>
  )
}
