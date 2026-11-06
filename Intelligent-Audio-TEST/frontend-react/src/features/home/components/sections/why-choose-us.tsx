import { Link } from '@tanstack/react-router'
import { ArrowUpRight } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

import { WHY_CHOOSE_US } from '../../constants'

/**
 * ③ 为什么选择本平台（03_首页.md §3.4）：六卡价值主张。
 */
export function WhyChooseUsSection({ className }: { className?: string }) {
  return (
    <section
      aria-labelledby='home-why-heading'
      className={cn(className, 'px-6 pt-16 sm:px-10 lg:pt-24')}
    >
      <div className='mx-auto max-w-6xl'>
        <AnimateInView>
          <p className='text-primary mb-4 text-xs font-semibold tracking-widest'>
            {WHY_CHOOSE_US.eyebrow}
          </p>
          <h2
            id='home-why-heading'
            className='max-w-4xl text-3xl leading-tight font-semibold tracking-tight text-balance sm:text-4xl'
          >
            {WHY_CHOOSE_US.heading}
          </h2>
          <p className='text-muted-foreground mt-5 max-w-3xl text-base leading-8 text-pretty'>
            {WHY_CHOOSE_US.subtext}
          </p>
        </AnimateInView>
        <div className='mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
          {WHY_CHOOSE_US.reasons.map((reason, i) => (
            <AnimateInView key={reason.title} delay={i * 50} className='min-w-0'>
              <Card key={reason.title} className='min-w-0 gap-4 rounded-2xl py-6'>
                <CardHeader className='gap-4 px-6'>
                  <div className='bg-primary/5 text-primary flex size-10 items-center justify-center rounded-xl'>
                    <reason.icon aria-hidden='true' className='size-5' />
                  </div>
                  <CardTitle>
                    <h3 className='text-lg font-semibold text-balance'>
                      {reason.title}
                    </h3>
                  </CardTitle>
                </CardHeader>
                <CardContent className='text-muted-foreground px-6 text-sm leading-7 text-pretty'>
                  {reason.description}
                </CardContent>
              </Card>
            </AnimateInView>
          ))}
        </div>
        <div className='mt-7 flex flex-wrap gap-x-7 gap-y-3'>
          {WHY_CHOOSE_US.footerLinks.map((link) =>
            link.to.startsWith('#') ? (
              <Button
                key={link.label}
                variant='link'
                className='h-auto p-0 whitespace-normal'
                render={<a href={link.to} />}
              >
                {link.label}
                <ArrowUpRight aria-hidden='true' className='size-4' />
              </Button>
            ) : (
              <Button
                key={link.label}
                variant='link'
                className='h-auto p-0 whitespace-normal'
                render={<Link to={link.to} />}
              >
                {link.label}
                <ArrowUpRight aria-hidden='true' className='size-4' />
              </Button>
            )
          )}
        </div>
      </div>
    </section>
  )
}
