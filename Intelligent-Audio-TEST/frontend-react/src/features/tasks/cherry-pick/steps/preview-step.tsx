/**
 * 预览步骤（Step 3/4，18_挑选合并功能交互重设计.md §5.1 / §5.2 / §5.3，INT-2003）。
 * 头 3 枚摘要徽章（结果 / 来源任务 / 设备·用例）+ 四条预校验 Alert + 只读容器组成预览 + 页脚两钮。
 * 语义：合并不可逆，本步让用户看到「合并后会生成什么形状的容器」；编辑（勾选 / 移除 / 批量 /
 * 清空 / 另存挑选集）一律留在 Step 2 购物车——本步无复选框、无移除钮、无批量浮条。
 * 取数：`usePreviewComposition`（购物车快照 + POST /tasks/cherry-picks/preview，零新增接口）。
 * 主钮 `{n}` 口径 = `preview.totalResults`（有效条目数，已剔除失效），不取购物车 `total`。
 */
import { Info, Layers, ShoppingCart, TriangleAlert } from 'lucide-react'

import { usePreviewComposition } from '@/application/tasks/cherry-pick/use-preview-composition'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { PreviewComposition } from '@/features/tasks/cherry-pick/components/preview-composition'

export function PreviewStep({
  onGoCart,
  onGoCheckout,
}: {
  /** 返回购物车修改（Step 2；失效条目的移除动作也指回这里，§5.2 ②） */
  onGoCart: () => void
  onGoCheckout: () => void
}) {
  const { entries, summary, preview, loading, error, retry } = usePreviewComposition()

  const data = preview
  const invalidCount = data?.invalidResultIds.length ?? 0
  const failedCount = data?.executionStatusCounts?.failed ?? 0
  const mergeCount = data?.totalResults
  /** 未返回预览时禁用且不显示假数字（§5.2 ④）；无有效条目可合并时同样禁用 */
  const canCheckout = mergeCount != null && mergeCount > 0

  const footer = (
    <div className='flex flex-wrap items-center gap-2 border-t pt-3'>
      <Button variant='ghost' size='sm' onClick={onGoCart}>
        <ShoppingCart aria-hidden='true' className='size-3.5' />
        返回购物车修改
      </Button>
      <span className='text-muted-foreground/70 text-[11px]'>
        预览为只读：勾选 / 移除 / 批量移除 / 一键移除失效只在购物车进行
      </span>
      <div className='ml-auto'>
        <Button size='sm' disabled={!canCheckout} onClick={onGoCheckout}>
          {canCheckout ? `确认下单（${mergeCount}）` : '确认下单'}
        </Button>
      </div>
    </div>
  )

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto'>
      <section className='bg-card flex flex-col gap-3 rounded-xl border p-4'>
        <div className='flex flex-wrap items-center gap-2'>
          <h2 className='text-sm font-medium'>合并预览</h2>
          <Badge variant='outline' className='rounded-md px-1.5 text-[11px]'>
            只读
          </Badge>
          <span className='text-muted-foreground text-xs'>下单后将生成的容器组成</span>
        </div>

        {/* ① 头部摘要：只在本步骤出现一次（Step 4 已去重，§5.3） */}
        <div className='flex flex-wrap items-center gap-3'>
          {!data ? (
            // 未返回（加载中）或取数失败：徽章保留骨架位，不做假数字（§5.2 ⑦）
            <>
              <Skeleton className='h-5 w-24' />
              <Skeleton className='h-5 w-28' />
              <Skeleton className='h-5 w-40' />
            </>
          ) : (
            <>
              <StatusBadge variant='success' label={`结果 ${data.totalResults} 条`} />
              <StatusBadge variant='info' label={`来源任务 ${data.sourceTaskCount} 个`} />
              <StatusBadge
                variant='neutral'
                label={`设备 ${data.deviceIds.length} 台 / 用例 ${data.caseCount} 个`}
              />
            </>
          )}
        </div>

        {/* ② 预校验 Alert（前三条沿用现文案，失效条补「本次将合并 {m} 条」且动作指回购物车） */}
        {data && invalidCount > 0 && (
          <Alert variant='destructive' className='border-warning/40'>
            <TriangleAlert aria-hidden='true' />
            <AlertTitle className='text-warning'>
              {invalidCount} 条购物车条目已失效（源结果被删除），下单时将跳过，本次将合并{' '}
              {mergeCount ?? 0} 条
            </AlertTitle>
            <AlertDescription>
              <Button
                variant='ghost'
                size='xs'
                className='text-warning mt-1 h-6'
                onClick={onGoCart}
              >
                返回购物车移除
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* 执行失败条目是正常业务态：失败 / 部分失败的任务本身即可被挑选合并（§5.5.4） */}
        {data && failedCount > 0 && (
          <Alert className='border-info/40'>
            <Info aria-hidden='true' />
            <AlertTitle className='text-info'>
              {failedCount} 条结果执行失败，合并后按原状态保留
            </AlertTitle>
            <AlertDescription>
              执行失败 / 部分失败的任务本身即可被挑选合并，失败条目按原状态呈现。
            </AlertDescription>
          </Alert>
        )}

        {data && (data.duplicates?.length ?? 0) > 0 && (
          <Alert className='border-info/40'>
            <Layers aria-hidden='true' />
            <AlertTitle className='text-info'>
              同设备同用例存在多来源结果 {data.duplicates.length} 组，合并将全部保留并标注来源
            </AlertTitle>
            <AlertDescription>
              预览与合并结果均按来源任务分组展示，重复结果不会丢失。
            </AlertDescription>
          </Alert>
        )}

        {data?.configInconsistent && (
          <Alert variant='destructive' className='border-warning/40'>
            <TriangleAlert aria-hidden='true' />
            <AlertTitle className='text-warning'>
              {data.sourceTaskCount} 个来源任务的任务级配置（
              {data.configFields?.join('、') ?? '配置'}）不一致，新任务默认取首个来源任务配置，可展开「任务级配置」覆盖
            </AlertTitle>
            <AlertDescription>
              下单步骤可展开「任务级配置」覆盖，确认下单前会再次确认。
            </AlertDescription>
          </Alert>
        )}
      </section>

      {/* ③ 组成预览（主体，只读四视图；任务视图默认） */}
      <PreviewComposition
        entries={entries}
        summary={summary}
        loading={loading}
        error={error}
        onRetry={retry}
        onGoCart={onGoCart}
        footer={footer}
      />
    </div>
  )
}
