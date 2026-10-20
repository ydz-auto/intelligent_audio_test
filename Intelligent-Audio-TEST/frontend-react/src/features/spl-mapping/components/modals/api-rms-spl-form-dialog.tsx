/**
 * 数字域 RMS-SPL 映射表单（§6.12 简化口径 INT-1031；Dialog sm:max-w-2xl）。
 * 标题「添加/编辑 RMS-SPL 映射」；字段（INT-1031 实测）：关联被测 API*（编辑态隐藏）/
 * 映射名称*。协议（默认 websocket）、供应商、参考声压级/参考线性增益/增益上下限等
 * 后端可缺省字段一律映射为默认值，不再出现在表单；主钮「保存」。
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

export function ApiRmsSplFormDialog(props: ApiRmsSplFormDialogProps) {
  const isEdit = props.mapping != null
  const { create, update } = useDigitalSplMutations()

  const [apiId, setApiId] = useState('')
  const [name, setName] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!props.open) return
    const mapping = props.mapping
    setApiId(mapping?.apiId != null ? String(mapping.apiId) : '')
    setName(mapping?.name ?? '')
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
        name: name.trim() || null,
        description: null,
        vendor: props.mapping?.vendor ?? null,
        protocol: (props.mapping?.protocol ?? 'websocket') as ApiRmsSplMapping['protocol'],
        referenceSpl: props.mapping?.referenceSpl ?? DEFAULT_REFERENCE_SPL,
        referenceGainLinear: props.mapping?.referenceGainLinear ?? DEFAULT_REFERENCE_GAIN_LINEAR,
        minGainLinear: props.mapping?.minGainLinear ?? DEFAULT_MIN_GAIN_LINEAR,
        maxGainLinear: props.mapping?.maxGainLinear ?? DEFAULT_MAX_GAIN_LINEAR,
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
            为被测 API 建立数字域 RMS→SPL 灵敏度映射（未校准时按参考基准线性近似）
          </DialogDescription>
        </DialogHeader>

        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
          {!isEdit && (
            <div className='space-y-2'>
              <Label required>关联被测 API</Label>
              <Select value={apiId} onValueChange={(value) => setApiId(value ?? '')}>
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
