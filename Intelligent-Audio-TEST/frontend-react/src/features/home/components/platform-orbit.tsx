import { Headphones } from 'lucide-react'

import { HOME_BRAND_NAME, ORBIT_ALGORITHM_NODES, ORBIT_NODES, HERO } from '../constants'
import { cn } from '@/lib/utils'

/**
 * 平台枢纽图（照 newAPI hero.tsx 枢纽图几何，03_首页.md §3.2）：
 * 双同心圆 + SVG 四象限连线 + 中心平台卡 + 四角功能节点卡（只上图标色）。
 * INT-421 口径：四角主节点与连线不变，外圈新增算法能力 floating 节点——
 * 虚线描边 + 半透明底（弱连接感），不接 SVG 连线、不进四象限几何。
 */
export function PlatformOrbit({ className }: { className?: string }) {
  return (
    <div
      role='img'
      aria-label='平台总览'
      className={cn('relative mx-auto w-full max-w-lg min-w-0', className)}
    >
      <div
        aria-hidden='true'
        className='relative h-80 sm:h-96 lg:h-[430px]'
      >
        <div className='border-primary/15 bg-primary/5 absolute top-1/2 left-1/2 size-64 -translate-x-1/2 -translate-y-1/2 rounded-full border sm:size-80' />
        <div className='border-primary/25 absolute top-1/2 left-1/2 size-44 -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed sm:size-56' />
        <svg
          className='text-primary/25 absolute inset-0 h-full w-full'
          viewBox='0 0 500 430'
          fill='none'
          preserveAspectRatio='none'
        >
          <path
            d='M85 75 C85 215 185 215 250 215 M415 100 C415 215 315 215 250 215 M85 325 C85 215 185 215 250 215 M415 350 C415 215 315 215 250 215'
            stroke='currentColor'
            strokeWidth='1.5'
          />
        </svg>
        <div className='bg-background/95 ring-background/40 absolute top-1/2 left-1/2 flex size-28 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center gap-2 rounded-[28px] border shadow-xl ring-8 sm:size-32'>
          <div className='bg-primary/10 text-primary flex size-12 items-center justify-center rounded-xl'>
            <Headphones aria-hidden='true' className='size-6' />
          </div>
          <span className='text-xs font-semibold tracking-wide'>
            {HOME_BRAND_NAME}
          </span>
        </div>
        {ORBIT_NODES.map((node) => (
          <div
            key={node.name}
            className={cn(
              'bg-card/90 absolute flex w-28 items-center gap-2.5 rounded-2xl border px-3 py-4 text-xs font-medium shadow-sm backdrop-blur-sm sm:w-36 sm:px-4 sm:text-sm',
              node.position,
              node.color
            )}
          >
            <span className='flex size-6 shrink-0 items-center justify-center'>
              <node.icon aria-hidden='true' className='size-5' />
            </span>
            {node.name}
          </div>
        ))}
        {ORBIT_ALGORITHM_NODES.map((node) => (
          <div
            key={node.name}
            className={cn(
              'bg-card/60 border-dashed absolute flex w-20 flex-col items-center gap-1 rounded-xl border px-2 py-2 text-[11px] font-medium leading-none backdrop-blur-sm sm:w-24 sm:px-3 sm:py-2.5 sm:text-xs',
              node.position,
              node.color,
              node.flagship && 'ring-primary/30 ring-1'
            )}
          >
            <span className='flex size-5 shrink-0 items-center justify-center'>
              <node.icon aria-hidden='true' className='size-4' />
            </span>
            <span className='text-center'>{node.name}</span>
          </div>
        ))}
      </div>
      <p
        aria-hidden='true'
        className='text-muted-foreground text-center text-xs font-medium tracking-wide'
      >
        {HERO.orbitCaption}
      </p>
    </div>
  )
}
