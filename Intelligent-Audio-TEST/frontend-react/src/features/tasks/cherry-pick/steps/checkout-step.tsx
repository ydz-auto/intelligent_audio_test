/**
 * 下单步骤（Step 4/4，18_挑选合并交互重设计.md §5.3，INT-600）。
 * 三出口 RadioGroup（合并/重新执行/重新评估）+ 合并字段 + 任务级配置折叠区 +
 * configInconsistent 强制确认 → POST /cart/checkout。
 */
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'

import { useCherryPickCheckout } from '@/application/tasks/cherry-pick/use-cherry-pick-checkout'
import { useCherryPickPreview } from '@/application/tasks/cherry-pick/use-cherry-pick-preview'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { CheckoutAction } from '@/domain/models/cherryPick'
import { CHECKOUT_ACTIONS } from '@/features/tasks/cherry-pick/constants'
import { cn } from '@/lib/utils'

export function CheckoutStep({
  onGoReview,
  onDone,
}: {
  onGoReview: () => void
  /** 下单成功（已跳转详情） */
  onDone: () => void
}) {
  const navigate = useNavigate()
  const preview = useCherryPickPreview()
  const checkout = useCherryPickCheckout()
  const total = usePickCartStore((s) => s.total)
  const refreshCart = usePickCartStore((s) => s.refreshCart)

  const [action, setAction] = useState<CheckoutAction>('merge')
  const [taskName, setTaskName] = useState('')
  const [description, setDescription] = useState('')
  const [algorithmType, setAlgorithmType] = useState('')
  const [algorithmParams, setAlgorithmParams] = useState('')
  const [configJson, setConfigJson] = useState('')
  const [configOpen, setConfigOpen] = useState(false)
  const [forcedOpen, setForcedOpen] = useState(false)

  const data = preview.data
  const configInconsistent = data?.configInconsistent ?? false
  const isMerge = action === 'merge'

  /** JSON 覆盖解析（空 → null 不发送；非法 → {ok:false} 拦截） */
  const parseJsonOverride = (
    text: string
  ): { ok: true; value: Record<string, unknown> } | { ok: false } | null => {
    if (!text.trim()) return null
    try {
      const parsed = JSON.parse(text)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return { ok: true, value: parsed as Record<string, unknown> }
      }
      return { ok: false }
    } catch {
      return { ok: false }
    }
  }

  const handleConfirm = async () => {
    if (configInconsistent) {
      setForcedOpen(true)
      return
    }
    await doCheckout()
  }

  const doCheckout = async () => {
    const name =
      action === 'merge'
        ? taskName.trim()
        : action === 'reexecute'
          ? taskName.trim() || `重执行-${Date.now() % 100000}`
          : undefined
    if (action === 'merge' && !name) {
      toast.error('新任务名称必填')
      return
    }
    const paramsParsed = parseJsonOverride(algorithmParams)
    const configParsed = parseJsonOverride(configJson)
    if (paramsParsed && !paramsParsed.ok) {
      toast.error('算法参数覆盖不是合法 JSON 对象')
      return
    }
    if (configParsed && !configParsed.ok) {
      toast.error('任务配置覆盖不是合法 JSON 对象')
      return
    }
    const result = await checkout.mutateAsync({
      action,
      name,
      description: description.trim() || undefined,
      algorithm_type: algorithmType.trim() || undefined,
      algorithm_params: paramsParsed?.ok ? paramsParsed.value : undefined,
      config: configParsed?.ok ? configParsed.value : undefined,
    })
    await refreshCart()
    const id = result.taskId
    if (action === 'merge') {
      toast.success(`挑选合并任务已创建（ID ${id}），可手动生成报告`)
      // 落点①（18 §5.5.3）：合并成功直达容器详情「组成」锚点，由详情页滚到组成区并高亮，
      // 不落在空的结果列表 / 关联用例上。
      void navigate({
        to: '/tasks/$tab',
        params: { tab: String(id) },
        hash: 'composition',
      })
    } else if (action === 'reexecute') {
      toast.success(`重执行任务已创建并启动（ID ${id}）`)
      void navigate({ to: '/tasks/$tab', params: { tab: String(id) } })
    } else {
      toast.success(`已对 ${data?.sourceTaskCount ?? 1} 个来源任务发起重新评估`)
    }
    onDone()
  }

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto'>
      <div className='grid gap-2 sm:grid-cols-3'>
        {CHECKOUT_ACTIONS.map((act) => {
          const active = action === act.key
          return (
            <button
              key={act.key}
              type='button'
              data-testid={`checkout-action-${act.key}`}
              className={cn(
                'rounded-lg border px-3 py-2.5 text-left transition-colors',
                active
                  ? 'border-primary bg-primary/[0.06] ring-primary/30 dark:bg-primary/10'
                  : 'hover:bg-muted/50'
              )}
              onClick={() => setAction(act.key)}
            >
              <span className='flex items-center gap-2 text-sm font-medium'>
                <span
                  className={cn(
                    'flex size-4 items-center justify-center rounded-full border',
                    active ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40'
                  )}
                >
                  {active && <span className='size-1.5 rounded-full bg-current' />}
                </span>
                {act.label}
              </span>
              <span className='text-muted-foreground mt-1 block text-xs leading-relaxed'>
                {act.description}
              </span>
            </button>
          )
        })}
      </div>

      {(data?.invalidResultIds.length ?? 0) > 0 && (
        <Alert variant='destructive' className='border-warning/40'>
          <AlertTitle className='text-warning'>
            {data?.invalidResultIds.length} 条失效条目下单时将跳过，可返回复核移除
          </AlertTitle>
          <AlertDescription>失效条目（源结果已删除）在出清时保留展示。</AlertDescription>
        </Alert>
      )}

      {isMerge && (
        <div className='flex flex-col gap-3'>
          <div className='flex flex-wrap gap-3'>
            <StatusBadge variant='success' label={`结果 ${data?.totalResults ?? total} 条`} />
            <StatusBadge variant='info' label={`来源任务 ${data?.sourceTaskCount ?? '—'} 个`} />
            <StatusBadge variant='neutral' label={`设备 ${data?.deviceIds.length ?? '—'} 台 / 用例 ${data?.caseCount ?? '—'} 个`} />
          </div>

          <div className='flex flex-col gap-2'>
            <Label htmlFor='checkout-name'>新任务名称（必填）</Label>
            <Input
              id='checkout-name'
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              placeholder='例如：远场高置信度结果合并验证'
              maxLength={60}
            />
          </div>
          <div className='flex flex-col gap-2'>
            <Label htmlFor='checkout-desc'>新任务描述（可选）</Label>
            <Textarea
              id='checkout-desc'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder='描述挑选合并的背景与目的'
              rows={2}
            />
          </div>

          <Collapsible open={configOpen} onOpenChange={setConfigOpen}>
            <CollapsibleTrigger
              render={
                <button type='button' className='text-primary flex items-center gap-1 text-sm'>
                  {configOpen ? (
                    <ChevronDown aria-hidden='true' className='size-4' />
                  ) : (
                    <ChevronRight aria-hidden='true' className='size-4' />
                  )}
                  任务级配置（可选，默认取首个来源任务）
                </button>
              }
            />
            <CollapsibleContent>
              <div className='mt-2 grid gap-2 rounded-lg border p-3 text-xs'>
                <div className='flex flex-col gap-1'>
                  <Label>算法类型覆盖</Label>
                  <Input
                    value={algorithmType}
                    onChange={(e) => setAlgorithmType(e.target.value)}
                    placeholder='默认取首个来源任务算法'
                    aria-label='算法类型覆盖'
                  />
                </div>
                <div className='flex flex-col gap-1'>
                  <Label>算法参数覆盖（JSON）</Label>
                  <Textarea
                    value={algorithmParams}
                    onChange={(e) => setAlgorithmParams(e.target.value)}
                    placeholder='可选，如 { "beam_size": 8 }'
                    aria-label='算法参数覆盖'
                    rows={2}
                    className='font-mono'
                  />
                </div>
                <div className='flex flex-col gap-1'>
                  <Label>任务配置覆盖（JSON）</Label>
                  <Textarea
                    value={configJson}
                    onChange={(e) => setConfigJson(e.target.value)}
                    placeholder='可选，如 { "concurrent_tasks": 4 }'
                    aria-label='任务配置覆盖'
                    rows={2}
                    className='font-mono'
                  />
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      )}

      {action === 'reexecute' && (
        <div className='flex flex-col gap-2'>
          <Label htmlFor='reexecute-name'>重执行任务名称（可选，默认自动命名）</Label>
          <Input
            id='reexecute-name'
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            placeholder='留空将自动命名'
            maxLength={60}
          />
        </div>
      )}

      <div className='flex items-center justify-between border-t pt-3'>
        <Button variant='ghost' size='sm' onClick={onGoReview}>
          返回复核
        </Button>
        <Button
          size='sm'
          disabled={total === 0 || checkout.isPending}
          onClick={handleConfirm}
        >
          {checkout.isPending ? '下单中…' : '确认下单'}
        </Button>
      </div>

      <ConfirmDialog
        open={forcedOpen}
        onOpenChange={setForcedOpen}
        title='确认合并？'
        desc={`所选结果来自 ${data?.sourceTaskCount ?? 1} 个来源任务，其任务级配置（${
          data?.configFields?.join('、') ?? '配置'
        }）不一致。合并新任务将默认取首个来源任务配置，您可展开「任务级配置」覆盖。是否继续合并？`}
        confirmText='继续合并'
        cancelBtnText='返回修改'
        handleConfirm={async () => {
          setForcedOpen(false)
          await doCheckout()
        }}
      />
    </div>
  )
}
