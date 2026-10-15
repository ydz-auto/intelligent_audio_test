import { Megaphone, ChevronDown } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

import { FAQ } from '../../constants'

/**
 * ⑧ 常见问题（03_首页.md §3.9）：左标题+公告行，右 Accordion 五问。
 * 基座 components/ui 无 accordion——以 Collapsible 组合出同版式（红线③不动 ui 目录）。
 */
export function FaqSection({ className }: { className?: string }) {
  return (
    <section
      aria-labelledby='home-faq-heading'
      className={cn(className, 'px-6 py-16 sm:px-10 lg:py-24')}
    >
      <div className='mx-auto grid max-w-6xl gap-6 lg:grid-cols-[0.65fr_1fr] lg:gap-16'>
        <AnimateInView>
          <div>
            <h2
              id='home-faq-heading'
              className='text-2xl font-medium tracking-tight sm:text-3xl'
            >
              {FAQ.heading}
            </h2>
            <p className='text-muted-foreground mt-4 text-sm leading-7'>
              {FAQ.subtext}
            </p>
            <div className='bg-muted/30 text-muted-foreground mt-6 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs'>
              <Megaphone aria-hidden='true' className='size-3.5' />
              {FAQ.notice}
            </div>
          </div>
        </AnimateInView>
        <div>
          {FAQ.items.map((item, i) => (
            <Collapsible key={item.id} defaultOpen={i === 0}>
              <div className='border-b'>
                <CollapsibleTrigger className='group text-foreground flex w-full items-center justify-between gap-4 py-5 text-left text-base font-medium focus-visible:outline-2 focus-visible:outline-offset-4'>
                  {item.question}
                  <ChevronDown
                    aria-hidden='true'
                    className='text-muted-foreground size-4 shrink-0 transition-transform group-data-[panel-open]:rotate-180'
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className='CollapsibleContent'>
                  <p className='text-muted-foreground pb-5 leading-7'>
                    {item.answer}
                  </p>
                </CollapsibleContent>
              </div>
            </Collapsible>
          ))}
        </div>
      </div>
    </section>
  )
}
