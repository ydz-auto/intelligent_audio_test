/**
 * 复核步骤（Step 3/4，18_挑选合并交互重设计.md §5.2，INT-600）。
 * 清单核对摘要（3 StatBadge）+ 失效/重复/配置差异 Alert + 购物车树（编辑态）+ 确认下单。
 * 复核摘要 = POST /tasks/cherry-picks/preview 实测返回（零新增接口）。
 */
import { ClipboardCheck, Layers, Save, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useCherryPickPreview } from '@/application/tasks/cherry-pick/use-cherry-pick-preview'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { CartPanel } from '@/features/tasks/cherry-pick/components/cart-panel'
import { SavePickSetDialog } from '@/features/tasks/cherry-pick/components/save-pick-set-dialog'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'

export function ReviewStep({
  onGoPick,
  onGoCheckout,
}: {
  onGoPick: () => void
  onGoCheckout: () => void
}) {
  const preview = useCherryPickPreview()
  const total = usePickCartStore((s) => s.total)
  const data = preview.data
  const [clearOpen, setClearOpen] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      <div className='flex flex-wrap items-center gap-3'>
        <StatusBadge variant='success' label={`结果 ${data?.totalResults ?? total} 条`} />
        <StatusBadge variant='info' label={`来源任务 ${data?.sourceTaskCount ?? '—'} 个`} />
        <StatusBadge
          variant='neutral'
          label={`设备 ${data?.deviceIds.length ?? '—'} 台 / 用例 ${data?.caseCount ?? '—'} 个`}
        />
      </div>

      {preview.isLoading ? (
        <div className='flex flex-col gap-2'>
          <Skeleton className='h-8 w-full' />
          <Skeleton className='h-24 w-full' />
        </div>
      ) : (
        <>
          {(data?.invalidResultIds.length ?? 0) > 0 && (
            <Alert variant='destructive' className='border-warning/40'>
              <TriangleAlert aria-hidden='true' />
              <AlertTitle className='text-warning'>
                {data?.invalidResultIds.length} 条购物车条目已失效（源结果被删除），下单时将跳过，可一键移除
              </AlertTitle>
              <AlertDescription>
                <Button
                  variant='ghost'
                  size='xs'
                  className='text-warning mt-1 h-6'
                  onClick={async () => {
                    await usePickCartStore.getState().removeInvalid()
                  }}
                >
                  一键移除失效
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {(data?.duplicates?.length ?? 0) > 0 && (
            <Alert className='border-info/40'>
              <Layers aria-hidden='true' />
              <AlertTitle className='text-info'>
                同设备同用例存在多来源结果 {data?.duplicates.length} 组，合并将全部保留并标注来源
              </AlertTitle>
              <AlertDescription>
                复核摘要与合并结果均按来源任务分组展示，重复结果不会丢失。
              </AlertDescription>
            </Alert>
          )}
          {data?.configInconsistent && (
            <Alert variant='destructive' className='border-warning/40'>
              <TriangleAlert aria-hidden='true' />
              <AlertTitle className='text-warning'>
                {data?.sourceTaskCount} 个来源任务的任务级配置（
                {data?.configFields?.join('、') ?? '配置'}）不一致，新任务默认取首个来源任务配置，可展开「任务级配置」覆盖
              </AlertTitle>
              <AlertDescription>
                下单步骤可展开「任务级配置」覆盖，确认下单前会再次确认。
              </AlertDescription>
            </Alert>
          )}
        </>
      )}

      <div className='min-h-0 flex-1 overflow-y-auto rounded-lg border'>
        <CartPanel showFooter={false} />
      </div>

      <div className='flex flex-wrap items-center gap-2 border-t pt-3'>
        <Button variant='ghost' size='sm' onClick={onGoPick}>
          <ClipboardCheck aria-hidden='true' className='size-3.5' />
          返回挑选
        </Button>
        <Button
          variant='outline'
          size='sm'
          className='text-destructive hover:text-destructive'
          disabled={total === 0}
          onClick={() => setClearOpen(true)}
        >
          清空购物车
        </Button>
        <Button
          variant='outline'
          size='sm'
          className='gap-1.5'
          disabled={total === 0}
          onClick={() => setSaveOpen(true)}
        >
          <Save aria-hidden='true' className='size-3.5' />
          另存为挑选集
        </Button>
        <div className='ml-auto'>
          <Button size='sm' disabled={total === 0} onClick={onGoCheckout}>
            确认下单（{total}）
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title='清空购物车'
        desc={`将清空购物车全部 ${total} 条结果，是否继续？`}
        destructive
        confirmText='继续'
        handleConfirm={async () => {
          await usePickCartStore.getState().clearCart()
          setClearOpen(false)
          toast.success('购物车已清空')
        }}
      />
      <SavePickSetDialog open={saveOpen} onOpenChange={setSaveOpen} />
    </div>
  )
}
