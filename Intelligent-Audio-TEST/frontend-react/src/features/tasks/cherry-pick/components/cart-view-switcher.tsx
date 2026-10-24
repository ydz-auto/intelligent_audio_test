/**
 * 购物车视图切换器（18_挑选合并交互重设计.md §4.2，INT-1128 / INT-1694）。
 * 「任务视图（默认）｜用例视图｜设备视图｜结果类型视图」——切换即时生效，
 * 各视图共享同一购物车条目集（usePickCartStore 单例镜像）与 selectedEntryIds，
 * 不改变已勾选移除选择态与失效标记（§4.2）。
 * INT-1694 二次口径：任务视图 = 任务在第一级、任务下再分三子模式；
 * 用例/设备/结果类型三视图 = 任务在最末一级（叶的前一级）。
 */
import { ClipboardList, ListChecks, Smartphone, Tag } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** 购物车视图：任务视图（默认，任务首级）/ 用例 / 设备 / 结果类型（任务末级） */
export type CartView = 'task' | 'case' | 'device' | 'resultType'

export function CartViewSwitcher({
  view,
  onChange,
  showResultType = true,
  className,
}: {
  view: CartView
  onChange: (view: CartView) => void
  /** 结果类型种类 <2 时不渲染「结果类型视图」入口（负责人 2026-10-24T12:39Z 追加口径） */
  showResultType?: boolean
  className?: string
}) {
  return (
    <div
      className={cn('bg-muted/60 flex items-center gap-0.5 rounded-lg p-0.5', className)}
    >
      <Button
        variant={view === 'task' ? 'default' : 'ghost'}
        size='sm'
        className='h-6 gap-1 px-2 text-xs'
        onClick={() => onChange('task')}
      >
        <ClipboardList aria-hidden='true' className='size-3.5' />
        任务视图
      </Button>
      <Button
        variant={view === 'case' ? 'default' : 'ghost'}
        size='sm'
        className='h-6 gap-1 px-2 text-xs'
        onClick={() => onChange('case')}
      >
        <ListChecks aria-hidden='true' className='size-3.5' />
        用例视图
      </Button>
      <Button
        variant={view === 'device' ? 'default' : 'ghost'}
        size='sm'
        className='h-6 gap-1 px-2 text-xs'
        onClick={() => onChange('device')}
      >
        <Smartphone aria-hidden='true' className='size-3.5' />
        设备视图
      </Button>
      {showResultType && (
        <Button
          variant={view === 'resultType' ? 'default' : 'ghost'}
          size='sm'
          className='h-6 gap-1 px-2 text-xs'
          onClick={() => onChange('resultType')}
        >
          <Tag aria-hidden='true' className='size-3.5' />
          结果类型视图
        </Button>
      )}
    </div>
  )
}
