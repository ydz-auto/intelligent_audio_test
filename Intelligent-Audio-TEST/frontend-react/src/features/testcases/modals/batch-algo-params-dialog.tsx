/**
 * 批量设置用例专属参数弹窗（11_用例域.md §5.3.1，Dialog sm:max-w-2xl）。
 * 算法类型*（Select，MOCK_ALGORITHMS）→ 参数配置 DynamicForm（按该算法 schema，
 * 空态「该算法暂无参数配置」）+ 轮次范围三档（所有轮次统一/指定轮次统一/逐轮设置每轮可不同，
 * §5.3.5 口径；负责人反馈「其他批量操作也是三档轮次范围逐项可用」）。
 * 可视稿演示态：提交走 toast；数据契约 algorithmType/params/roundMode/rounds 留接线批次。
 */
import { useState } from 'react'
import { toast } from 'sonner'

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
import { Switch } from '@/components/ui/switch'
import { MOCK_ALGORITHMS } from '@/domain/models/algorithm'
import {
  createRoundScope,
  RoundScopeThreeField,
  usePerRoundValue,
} from '@/features/testcases/modals/batch-shared'
import {
  ALGO_SCHEMAS,
  type AlgorithmParamField,
} from '@/features/testcases/modals/round-config/algo-params-step'

/** DynamicForm 字段渲染（受控；§5.3.1 按算法 schema 逐字段） */
function AlgoParamInput({
  field,
  value,
  onChange,
}: {
  field: AlgorithmParamField
  value: string | boolean | undefined
  onChange: (v: string | boolean) => void
}) {
  if (field.type === 'switch') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Switch
          checked={Boolean(value ?? field.default)}
          onCheckedChange={(v) => onChange(v)}
          aria-label={field.label}
        />
      </div>
    )
  }
  if (field.type === 'select') {
    return (
      <div className='space-y-1.5'>
        <Label className='text-sm'>{field.label}</Label>
        <Select
          value={String(value ?? field.default ?? '')}
          onValueChange={(v) => v != null && onChange(v)}
        >
          <SelectTrigger size='sm' className='h-8 w-full'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {field.options?.map((o) => (
              <SelectItem key={o} value={o}>
                {o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }
  return (
    <div className='space-y-1.5'>
      <Label className='text-sm'>{field.label}</Label>
      <Input
        type={field.type === 'number' ? 'number' : 'text'}
        value={String(value ?? field.default ?? '')}
        placeholder={field.placeholder}
        className='h-8'
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

/** 参数配置节（受控；key=algorithmType 强制重置，避免算法切换残留旧字段值） */
function AlgoParamForm({
  algorithmType,
  value,
  onChange,
}: {
  algorithmType: string
  value: Record<string, string | boolean>
  onChange: (v: Record<string, string | boolean>) => void
}) {
  const schema = ALGO_SCHEMAS[algorithmType]

  if (!schema) {
    return (
      <div className='border-border/60 rounded-lg border border-dashed px-3 py-6 text-center'>
        <p className='text-muted-foreground text-sm'>该算法暂无参数配置</p>
      </div>
    )
  }

  return (
    <div className='space-y-3'>
      {schema.map((group) => (
        <div key={group.title} className='overflow-hidden rounded-lg border'>
          <div className='bg-muted/50 border-b px-3 py-2 text-sm font-medium'>
            {group.title}
          </div>
          <div className='grid gap-x-6 gap-y-3 p-3 sm:grid-cols-2 lg:grid-cols-3'>
            {group.fields.map((f) => (
              <AlgoParamInput
                key={f.code}
                field={f}
                value={value[f.code]}
                onChange={(v) => onChange({ ...value, [f.code]: v })}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function BatchAlgoParamsDialog({
  open,
  onOpenChange,
  count,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
}) {
  const [algorithmType, setAlgorithmType] = useState('')
  const [scope, setScope] = useState(createRoundScope())
  const {
    current: params,
    setCurrent: setParams,
    resetValue: resetParams,
  } = usePerRoundValue<Record<string, string | boolean>>({}, scope)

  const handleAlgorithmChange = (v: string | null) => {
    setAlgorithmType(v ?? '')
    resetParams()
  }

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
            <Select value={algorithmType} onValueChange={handleAlgorithmChange}>
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择算法' />
              </SelectTrigger>
              <SelectContent>
                {MOCK_ALGORITHMS.filter((a) => a.enabled).map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {algorithmType ? (
            <>
              {scope.mode === 'per_round' && (
                <p className='rounded-md bg-muted/60 px-2 py-1.5 text-xs'>
                  当前编辑第 {scope.activeRound} 轮参数，可逐轮分别配置
                </p>
              )}
              <AlgoParamForm
                key={algorithmType}
                algorithmType={algorithmType}
                value={params}
                onChange={setParams}
              />
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
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              toast.success(`批量操作执行成功（更新 ${count} 个）`)
              onOpenChange(false)
            }}
          >
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
