import { Link } from '@tanstack/react-router'
import { ArrowRight, ArrowUpRight } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { cn } from '@/lib/utils'

import { QUICK_START } from '../../constants'

/**
 * ② 从这里开始（03_首页.md §3.3）：五步流程条 + 双入口卡。
 */
export function QuickStartSection({ className }: { className?: string }) {
  return (
    <section
      aria-labelledby='home-quickstart-heading'
      className={cn(className, 'px-6 pt-16 sm:px-10 lg:pt-24')}
    >
      <div className='mx-auto max-w-6xl'>
        <AnimateInView>
          <p className='text-muted-foreground mb-4 font-mono text-xs tracking-widest'>
            {QUICK_START.eyebrow}
          </p>
          <h2
            id='home-quickstart-heading'
            className='max-w-3xl text-3xl leading-tight font-medium tracking-tight sm:text-4xl'
          >
            {QUICK_START.heading}
          </h2>
          <p className='text-muted-foreground mt-4 max-w-2xl text-sm leading-7'>
            {QUICK_START.subtext}
          </p>
        </AnimateInView>

        <AnimateInView delay={80}>
          <div className='mt-8 flex flex-wrap items-center gap-x-3 gap-y-4'>
            {QUICK_START.steps.map((step, i) => (
              <div key={step.name} className='flex items-center gap-3'>
                <div className='flex items-center gap-2.5'>
                  <span className='bg-primary/10 text-primary flex size-7 items-center justify-center rounded-full text-xs font-semibold'>
                    {i + 1}
                  </span>
                  <div>
                    <p className='text-sm font-medium'>{step.name}</p>
                    <p className='text-muted-foreground text-xs'>
                      {step.description}
                      {i === 0 && (
                        <span className='ms-1 hidden text-xs lg:inline'>
                          （{QUICK_START.algorithmNote}）
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                {i < QUICK_START.steps.length - 1 && (
                  <ArrowRight
                    aria-hidden='true'
                    className='text-muted-foreground size-4'
                  />
                )}
              </div>
            ))}
          </div>
        </AnimateInView>

        <div className='mt-8 grid gap-4 lg:grid-cols-2'>
          {QUICK_START.cards.map((card, i) => (
            <AnimateInView key={card.key} delay={i * 50} className='min-w-0'>
              <Card className='min-w-0 gap-5 rounded-2xl pt-6'>
                <CardHeader className='gap-5 px-6'>
                  <div
                    className={`flex size-11 items-center justify-center rounded-xl ${card.color}`}
                  >
                    <card.icon aria-hidden='true' className='size-5' />
                  </div>
                  <CardTitle>
                    <h3 className='text-xl leading-7 font-semibold'>
                      {card.title}
                    </h3>
                  </CardTitle>
                </CardHeader>
                <CardContent className='flex-1 px-6'>
                  <p className='text-muted-foreground text-sm leading-7'>
                    {card.description}
                  </p>
                  <div className='mt-5 flex flex-wrap gap-2'>
                    {card.badges.map((badge) => (
                      <Badge key={badge} variant='secondary'>
                        {badge}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
                <CardFooter className='bg-transparent px-6 py-4'>
                  <Button
                    variant='link'
                    className='h-auto w-full justify-between p-0 text-left whitespace-normal'
                    render={<Link to={card.to} />}
                  >
                    {card.action}
                    <ArrowUpRight aria-hidden='true' className='size-4' />
                  </Button>
                </CardFooter>
              </Card>
            </AnimateInView>
          ))}
        </div>
      </div>
    </section>
  )
}
