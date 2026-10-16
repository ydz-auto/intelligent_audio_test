import { Link } from '@tanstack/react-router'
import { ArrowUpRight } from 'lucide-react'

import { AnimateInView } from '@/components/animate-in-view'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { TEST_OBJECT_ACCESS } from '../../constants'
import { AccessDemo } from '../access-demo'

/**
 * ⑤ 接入测试对象（03_首页.md §3.6，INT-420 负责人口径）：
 * 左三对象卡（被测设备/被测APP/被测API 各自「怎么接」+入口）+ 右接入演示三页签；
 * 示例值一律标注「示例数据」。公开门户区，展示层不涉权限（未登录亦可见）。
 */
export function TestObjectAccessSection({ className }: { className?: string }) {
  return (
    <section
      aria-labelledby='home-access-heading'
      className={cn(className, 'px-6 pt-16 sm:px-10 lg:pt-24')}
    >
      <div className='mx-auto max-w-6xl'>
        <AnimateInView>
          <div className='bg-muted/30 grid max-w-6xl gap-10 rounded-3xl border p-6 sm:p-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-12 lg:p-12'>
            <div className='min-w-0'>
              <p className='text-muted-foreground mb-5 font-mono text-xs tracking-widest'>
                {TEST_OBJECT_ACCESS.eyebrow}
              </p>
              <h2
                id='home-access-heading'
                className='text-3xl leading-tight font-medium tracking-tight sm:text-4xl'
              >
                {TEST_OBJECT_ACCESS.heading}
              </h2>
              <p className='text-muted-foreground mt-5 text-sm leading-7'>
                {TEST_OBJECT_ACCESS.subtext}
              </p>
              <div className='mt-8 space-y-4'>
                {TEST_OBJECT_ACCESS.objects.map((obj) => (
                  <div
                    key={obj.key}
                    className='bg-background/70 rounded-2xl border p-4'
                  >
                    <div className='flex items-center gap-3'>
                      <span className='bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg'>
                        <obj.icon aria-hidden='true' className='size-4' />
                      </span>
                      <p className='text-sm font-semibold'>{obj.name}</p>
                      <Button
                        variant='link'
                        className='ml-auto h-auto p-0 text-sm font-medium whitespace-normal'
                        render={<Link to={obj.to} />}
                      >
                        {obj.action}
                        <ArrowUpRight aria-hidden='true' className='size-4' />
                      </Button>
                    </div>
                    <p className='text-muted-foreground mt-1.5 text-xs leading-6'>
                      {obj.description}
                    </p>
                  </div>
                ))}
              </div>
              <Button
                variant='link'
                className='mt-6 h-auto p-0'
                render={<Link to='/user-guide' />}
              >
                {TEST_OBJECT_ACCESS.guideLink}
                <ArrowUpRight aria-hidden='true' className='size-4' />
              </Button>
            </div>
            <div className='min-w-0'>
              <AccessDemo />
            </div>
          </div>
        </AnimateInView>

        <div className='mx-auto grid max-w-6xl gap-5 pt-10 md:grid-cols-[1fr_auto] md:items-center'>
          <div>
            <h3 className='text-sm font-medium'>{TEST_OBJECT_ACCESS.tail.heading}</h3>
            <p className='text-muted-foreground mt-2 max-w-xl text-xs leading-6'>
              {TEST_OBJECT_ACCESS.tail.note}
            </p>
          </div>
          <div className='flex flex-wrap gap-3'>
            {TEST_OBJECT_ACCESS.tail.actions.map((action) => (
              <Button
                key={action.label}
                variant='outline'
                className='rounded-full'
                render={<Link to={action.to} />}
              >
                {action.label}
                <ArrowUpRight aria-hidden='true' className='size-4' />
              </Button>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
