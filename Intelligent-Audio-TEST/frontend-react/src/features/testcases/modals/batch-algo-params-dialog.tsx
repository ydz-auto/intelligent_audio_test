/**
 * 批量设置用例专属参数弹窗（11_用例域.md §5.3.1，Dialog sm:max-w-2xl；INT-710 真实数据接线）。
 * 算法类型*（Select，真实 GET /algorithm/options）→ 参数配置（DynamicForm 按该算法真实
 * form-schema GET /algorithm/form-schema/{type} 渲染，空态「该算法暂无参数配置」）+ 轮次范围
 * 三档（所有轮次统一/指定轮次统一/逐轮设置每轮可不同，§5.3.5 口径）。
 * 提交走 POST /testcases/batch（update_algorithm_params）：algorithm_params + round_mode/round_numbers。
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import {
  fetchAlgorithmFormSchema,
  type AlgorithmFormField,
} from '@/infrastructure/api/algorithm-form-api'
import {
  batchTestcaseAction,
  type TestcaseBatchPayload,
  type TestcaseRoundMode,
} from '@/infrastructure/api/testcases-batch-api'
import {
  createRoundScope,
  RoundScopeThreeField,
  usePerRoundValue,
} from '@/features/testcases/modals/batch-shared'
import { toast } from 'sonner'

/** DynamicForm 字段渲染（受控；照旧 Vue DynamicForm.vue component 分支） */
function AlgoParamInput({
  field,
  value,
  onChange,
}: {
  field: AlgorithmFormField
  value: string | boolean | undefined
  onChange: (v: string | boolean) => void
}) {
  const component = field.component ?? 'input'
  if (component === 'switch' || field.type === 'switch') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Switch
          checked={Boolean(value ?? field.defaultValue)}
          onCheckedChange={(v) => onChange(v)}
          aria-label={field.label}
        />
        {field.helpText && (
          <p className='text-muted-foreground/70 text-xs'>{field.helpText}</p>
        )}
      </div>
    )
  }
  if (component === 'select') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Select
          value={String(value ?? field.defaultValue ?? '')}
          onValueChange={(v) => v != null && onChange(v)}
        >
          <SelectTrigger size='sm' className='h-8 w-full'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map((o) => (
              <SelectItem key={o} value={o}>
                {o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {field.helpText && (
          <p className='text-muted-foreground/70 text-xs'>{field.helpText}</p>
        )}
      </div>
    )
  }
  if (component === 'code-editor' || field.type === 'json') {
    const textValue =
      value === undefined ? jsonDefault(field.defaultValue) : String(value)
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <textarea
          value={textValue}
          rows={4}
          aria-label={field.label}
          placeholder={field.helpText ?? undefined}
          className='border-border/60 bg-background focus:border-primary focus:ring-primary/20 min-h-0 w-full rounded-md border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2'
          onChange={(e) => onChange(e.target.value)}
        />
        {field.helpText && (
          <p className='text-muted-foreground/70 text-xs'>{field.helpText}</p>
        )}
      </div>
    )
  }
  if (component === 'input-number' || field.type === 'number') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Input
          type='number'
          value={String(value ?? field.defaultValue ?? '')}
          placeholder={field.helpText ?? undefined}
          className='h-8'
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    )
  }
  return (
    <div className='space-y-1.5'>
      <Label className='text-sm'>{field.label}</Label>
      <Input
        type='text'
        value={String(value ?? field.defaultValue ?? '')}
        placeholder={field.helpText ?? undefined}
        className='h-8'
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

function jsonDefault(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

/** 参数配置节（受控；key=algorithmType 强制重置，避免算法切换残留旧字段值） */
function AlgoParamForm({
  fields,
  value,
  onChange,
}: {
  fields: AlgorithmFormField[]
  value: Record<string, string | boolean>
  onChange: (v: Record<string, string | boolean>) => void
}) {
  if (fields.length === 0) {
    return (
      <div className='border-border/60 rounded-lg border border-dashed px-3 py-6 text-center'>
        <p className='text-muted-foreground text-sm'>该算法暂无参数配置</p>
      </div>
    )
  }
  return (
    <div className='grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3'>
      {fields.map((f) => (
        <AlgoParamInput
          key={f.code}
          field={f}
          value={value[f.code]}
          onChange={(v) => onChange({ ...value, [f.code]: v })}
        />
      ))}
    </div>
  )
}

export function BatchAlgoParamsDialog({
  open,
  onOpenChange,
  count,
  ids,
  roundCount,
  unknownRoundCount = 0,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
  /** 选中用例实际轮次数（config.rounds 派生；0=空态） */
  roundCount: number
  /** 选中用例中轮次未知（列表尚未加载）的条数 */
  unknownRoundCount?: number
}) {
  const { options: algorithmOptions, isLoading: loadingAlgorithms } =
    useAlgorithmOptions()
  const [algorithmType, setAlgorithmType] = useState('')
  const [scope, setScope] = useState(() => createRoundScope(roundCount))
  const [submitting, setSubmitting] = useState(false)
  const {
    current: params,
    setCurrent: setParams,
    resetValue: resetParams,
    perRound,
  } = usePerRoundValue<Record<string, string | boolean>>({}, scope)

  const schemaQuery = useQuery({
    queryKey: ['algorithm-form-schema', algorithmType],
    queryFn: () => fetchAlgorithmFormSchema(algorithmType),
    enabled: Boolean(algorithmType),
  })

  const handleAlgorithmChange = (v: string | null) => {
    setAlgorithmType(v ?? '')
    resetParams()
  }

  /** 展平（顶层 fields + 分组内 fields 按 uiOrder 归并；§5.3.1 参数表单逐字段） */
  const allFields = schemaQuery.data
    ? [
        ...schemaQuery.data.fields,
        ...schemaQuery.data.groups.flatMap((g) => g.fields),
      ].filter((f) => !f.hidden)
    : []

  const handleSubmit = async () => {
    if (!algorithmType) return
    let payload: TestcaseBatchPayload
    if (scope.mode === 'per_round') {
      // 逐轮设置：round_values = {轮次号: {params: {...}}}，仅含用户实际编辑过的轮次
      const roundValues: Record<string, unknown> = {}
      for (const [roundKey, roundParams] of Object.entries(perRound)) {
        if (!roundParams || Object.keys(roundParams).length === 0) continue
        roundValues[roundKey] = { params: roundParams }
      }
      if (Object.keys(roundValues).length === 0) {
        toast.error('请至少为一个轮次填写专属参数')
        return
      }
      payload = { roundMode: 'per_round', roundNumbers: [], roundValues }
    } else {
      payload = {
        algorithmParams: { ...params },
        roundMode: scope.mode as TestcaseRoundMode,
        roundNumbers:
          scope.mode === 'specific'
            ? scope.specificRounds
            : undefined,
      }
    }
    setSubmitting(true)
    try {
      await batchTestcaseAction('update_algorithm_params', ids, payload)
      toast.success(`批量操作执行成功（更新 ${count} 个）`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量设置专属参数失败')
    } finally {
      setSubmitting(false)
    }
  }

  /** 逐轮模式：任一编辑过的轮次有参数即可提交 */
  const canSubmit =
    scope.mode === 'per_round'
      ? Object.values(perRound).some((p) => Object.keys(p).length > 0)
      : Boolean(algorithmType)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>批量设置用例专属参数</DialogTitle>
          <DialogDescription>
            您勾选了 {count} 个用例，将统一设置其算法专属参数
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>算法类型 *</span>
            {loadingAlgorithms ? (
              <div className='flex h-8 items-center gap-2 rounded-md border px-3 text-sm'>
                <Spinner className='size-3.5' />
                加载算法列表...
              </div>
            ) : (
              <Select value={algorithmType} onValueChange={handleAlgorithmChange}>
                <SelectTrigger size='sm' className='h-8 w-full'>
                  <SelectValue placeholder='请选择算法' />
                </SelectTrigger>
                <SelectContent>
                  {algorithmOptions.map((a) => (
                    <SelectItem key={a.value} value={a.value}>
                      {a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          {algorithmType ? (
            <>
              {schemaQuery.isLoading ? (
                <div className='flex h-24 items-center justify-center gap-2 rounded-lg border text-sm text-muted-foreground'>
                  <Spinner className='size-4' />
                  正在加载算法参数表单...
                </div>
              ) : schemaQuery.isError ? (
                <div className='rounded-lg border px-3 py-6 text-center'>
                  <p className='text-destructive text-sm'>加载算法参数表单失败</p>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='mt-2 h-7'
                    onClick={() => void schemaQuery.refetch()}
                  >
                    重试
                  </Button>
                </div>
              ) : (
                <>
                  {scope.mode === 'per_round' && (
                    <p className='rounded-md bg-muted/60 px-2 py-1.5 text-xs'>
                      当前编辑第 {scope.activeRound} 轮参数，可逐轮分别配置
                    </p>
                  )}
                  <AlgoParamForm
                    key={algorithmType}
                    fields={allFields}
                    value={params}
                    onChange={setParams}
                  />
                </>
              )}
            </>
          ) : (
            <div className='border-border/60 rounded-lg border border-dashed px-3 py-6 text-center'>
              <p className='text-muted-foreground text-sm'>
                请先选择算法类型，参数表单将按算法 schema 加载
              </p>
            </div>
          )}

          <RoundScopeThreeField
            name='batch-algo-params-round'
            value={scope}
            onChange={setScope}
            roundCount={roundCount}
            unknownRoundCount={unknownRoundCount}
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || !canSubmit}>
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
