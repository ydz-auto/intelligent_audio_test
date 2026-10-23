/**
 * 数字域 RMS-SPL 映射表单（§6.12 简化口径 INT-1031 返工；Dialog sm:max-w-2xl）。
 * 标题「添加/编辑 RMS-SPL 映射」；字段=关联被测 API*（create-only，编辑态隐藏）/映射名称*
 * （必填）/参考声压级（30-120 默认 65，hint「未校准时的参考基准」）/参考线性增益（正数
 * 默认 1.0）/增益下限（默认 0.001「防静音限幅」）/增益上限（默认 10.0「防爆音限幅」）。
 * 供应商/协议不再出现在表单，提交映射 vendor=null、protocol=websocket；主钮「保存」。
 */
import { useEffect, useState } from 'react'
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
import type { ApiConfigRef, ApiRmsSplMapping } from '@/domain/models/digitalSpl'
import {
  DEFAULT_MAX_GAIN_LINEAR,
  DEFAULT_MIN_GAIN_LINEAR,
  DEFAULT_REFERENCE_GAIN_LINEAR,
  DEFAULT_REFERENCE_SPL,
} from '@/features/spl-mapping/constants'
import { useDigitalSplMutations } from '@/application/spl/useDigitalSplMappings'

export type ApiRmsSplFormDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mapping: ApiRmsSplMapping | null
  apis: ApiConfigRef[]
}

/** 正数数值解析：空/非正数回退默认（增益三字段不做必填校验，可带默认值） */
function parsePositiveNumeric(value: string, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

/** 参考声压级解析：限定 30-120，越界/空回退默认 65 */
function parseReferenceSpl(value: string, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) && n >= 30 && n <= 120 ? n : fallback
}

export function ApiRmsSplFormDialog(props: ApiRmsSplFormDialogProps) {
  const isEdit = props.mapping != null
  const { create, update } = useDigitalSplMutations()

  const [apiId, setApiId] = useState('')
  const [name, setName] = useState('')
  const [referenceSpl, setReferenceSpl] = useState(String(DEFAULT_REFERENCE_SPL))
  const [referenceGainLinear, setReferenceGainLinear] = useState(String(DEFAULT_REFERENCE_GAIN_LINEAR))
  const [minGainLinear, setMinGainLinear] = useState(String(DEFAULT_MIN_GAIN_LINEAR))
  const [maxGainLinear, setMaxGainLinear] = useState(String(DEFAULT_MAX_GAIN_LINEAR))
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!props.open) return
    const mapping = props.mapping
    setApiId(mapping?.apiId != null ? String(mapping.apiId) : '')
    setName(mapping?.name ?? '')
    setReferenceSpl(mapping?.referenceSpl != null ? String(mapping.referenceSpl) : String(DEFAULT_REFERENCE_SPL))
    setReferenceGainLinear(
      mapping?.referenceGainLinear != null ? String(mapping.referenceGainLinear) : String(DEFAULT_REFERENCE_GAIN_LINEAR)
    )
    setMinGainLinear(mapping?.minGainLinear != null ? String(mapping.minGainLinear) : String(DEFAULT_MIN_GAIN_LINEAR))
    setMaxGainLinear(mapping?.maxGainLinear != null ? String(mapping.maxGainLinear) : String(DEFAULT_MAX_GAIN_LINEAR))
  }, [props.open, props.mapping])

  if (!props.open) return null

  const apiOptions = props.apis.map((api) => ({
    value: String(api.id),
    label: api.vendor ? `${api.name}（${api.vendor}）` : api.name,
  }))

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('请输入映射名称')
      return
    }
    if (!isEdit && !apiId) {
      toast.error('请选择关联被测 API')
      return
    }
    setPending(true)
    try {
      const base = {
        name: name.trim(),
        description: null,
        vendor: null,
        protocol: 'websocket' as ApiRmsSplMapping['protocol'],
        referenceSpl: parseReferenceSpl(referenceSpl, DEFAULT_REFERENCE_SPL),
        referenceGainLinear: parsePositiveNumeric(referenceGainLinear, DEFAULT_REFERENCE_GAIN_LINEAR),
        minGainLinear: parsePositiveNumeric(minGainLinear, DEFAULT_MIN_GAIN_LINEAR),
        maxGainLinear: parsePositiveNumeric(maxGainLinear, DEFAULT_MAX_GAIN_LINEAR),
        calibrationStatus: null,
        calibrationPoints: [],
        createdAt: null,
        updatedAt: null,
      }
      if (isEdit && props.mapping) {
        await update.mutateAsync({ id: props.mapping.id, patch: base })
        toast.success('RMS-SPL 映射更新成功')
      } else {
        await create.mutateAsync({ ...base, apiId: Number(apiId) })
        toast.success('RMS-SPL 映射创建成功')
      }
      props.onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑 RMS-SPL 映射' : '添加 RMS-SPL 映射'}</DialogTitle>
          <DialogDescription>
            数字域 RMS→SPL 灵敏度映射：为被测 API 配置参考基准与增益限幅（未校准时按参考基准线性近似）
          </DialogDescription>
        </DialogHeader>

        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
          {!isEdit && (
            <div className='space-y-2'>
              <Label required>关联被测 API</Label>
              <Select
                value={apiId}
                onValueChange={(value) => setApiId(value ?? '')}
                items={apiOptions}
              >
                <SelectTrigger size='sm' className='w-full' aria-label='关联被测 API'>
                  <SelectValue placeholder='请选择被测 API（API 1:N 映射）' />
                </SelectTrigger>
                <SelectContent>
                  {apiOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className='space-y-2'>
            <Label required>映射名称</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder='请输入映射名称' aria-label='映射名称' />
          </div>
          <div className='space-y-2'>
            <Label>参考声压级（dB SPL）</Label>
            <Input
              type='number'
              min={30}
              max={120}
              step='0.1'
              value={referenceSpl}
              onChange={(e) => setReferenceSpl(e.target.value)}
              aria-label='参考声压级'
            />
            <p className='text-muted-foreground text-xs'>未校准时的参考基准（30-120 dB）</p>
          </div>
          <div className='space-y-2'>
            <Label>参考线性增益</Label>
            <Input
              type='number'
              min={0.001}
              step='0.001'
              value={referenceGainLinear}
              onChange={(e) => setReferenceGainLinear(e.target.value)}
              aria-label='参考线性增益'
            />
            <p className='text-muted-foreground text-xs'>未校准时的参考增益（正数）</p>
          </div>
          <div className='space-y-2'>
            <Label>增益下限</Label>
            <Input
              type='number'
              min={0.001}
              step='0.001'
              value={minGainLinear}
              onChange={(e) => setMinGainLinear(e.target.value)}
              aria-label='增益下限'
            />
            <p className='text-muted-foreground text-xs'>防静音限幅</p>
          </div>
          <div className='space-y-2'>
            <Label>增益上限</Label>
            <Input
              type='number'
              min={0.001}
              step='0.1'
              value={maxGainLinear}
              onChange={(e) => setMaxGainLinear(e.target.value)}
              aria-label='增益上限'
            />
            <p className='text-muted-foreground text-xs'>防爆音限幅</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleSave} disabled={pending}>
            {pending ? '保存中...' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
