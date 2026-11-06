/**
 * 预览步骤组成区薄壳（18_挑选合并功能交互重设计.md §5.2 ③/⑥/⑦/⑧，INT-2003）。
 * 预览不取容器端点（容器尚不存在）——条目来自购物车快照（`toPreviewCompositionEntries`），
 * 组成视图与容器详情同源：直接复用 `ContainerComposition mode='preview'`（四视图 + 只读 `CartTree`）。
 * 本壳只承担预览侧三态：加载骨架 / 购物车为空 / 预览失败（页内 `Empty` + 重试，**不弹 toast**，§5.2 ⑦）。
 * 纯 props，取数在 `usePreviewComposition`。
 */
import { ShoppingCart, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import type {
  CompositionEntry,
  CompositionSummary,
} from '@/domain/lib/container-composition'
import { ContainerComposition } from '@/features/tasks/detail/container-composition'

/** 错误 / 空态共用卡壳：与组成区同卡样式（bg-card / border / rounded-xl） */
function PreviewShell({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <section className='bg-card flex flex-col gap-3 rounded-xl border p-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <h2 className='text-sm font-medium'>组成预览</h2>
        <Badge variant='outline' className='rounded-md px-1.5 text-[11px]'>
          四视图 · 只读
        </Badge>
        <span className='text-muted-foreground/70 ml-auto shrink-0 text-[11px]'>
          按购物车快照展示，评估状态与分组标签在下单后可见
        </span>
      </div>
      {children}
      {footer}
    </section>
  )
}

export function PreviewComposition({
  entries,
  summary,
  loading,
  error,
  onRetry,
  onGoCart,
  footer,
}: {
  entries: CompositionEntry[]
  summary: CompositionSummary
  /** cart / preview 任一 pending（§5.2 ⑦：徽章骨架 + 树骨架 3 层） */
  loading: boolean
  /** 非 400 的预览失败（400 空购物车已兜底成空预览） */
  error: Error | null
  onRetry: () => void
  onGoCart: () => void
  /** 页脚（「返回购物车修改」/「确认下单（{n}）」），与组成区同一张卡（§5.2 ④） */
  footer?: ReactNode
}) {
  // 预览失败：树区页内 Empty + 重试，不弹 toast、不做假数字（§5.2 ⑦）
  if (!loading && error) {
    return (
      <PreviewShell footer={footer}>
        <Empty className='rounded-xl border border-dashed py-10'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <TriangleAlert aria-hidden='true' className='size-4' />
            </EmptyMedia>
            <EmptyTitle>合并预览失败</EmptyTitle>
            <EmptyDescription>预览摘要未取到，可重试</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button variant='outline' size='sm' onClick={onRetry}>
              重试
            </Button>
          </EmptyContent>
        </Empty>
      </PreviewShell>
    )
  }

  // 购物车为空：无从预览（§5.2 ⑦）
  if (!loading && entries.length === 0) {
    return (
      <PreviewShell footer={footer}>
        <Empty className='rounded-xl border border-dashed py-10'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <ShoppingCart aria-hidden='true' className='size-4' />
            </EmptyMedia>
            <EmptyTitle>购物车为空，暂无可预览的合并组成</EmptyTitle>
            <EmptyDescription>
              先从任务 / 用例 / 设备 / 结果类型任一层级勾选执行结果加入购物车
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button variant='outline' size='sm' onClick={onGoCart}>
              返回购物车
            </Button>
          </EmptyContent>
        </Empty>
      </PreviewShell>
    )
  }

  return (
    <ContainerComposition
      mode='preview'
      // 预览阶段没有容器：trace 恒 null，空态由本壳按购物车 / 错误状态判定
      sectionId={null}
      entries={entries}
      summary={summary}
      loading={loading}
      footer={footer}
    />
  )
}
