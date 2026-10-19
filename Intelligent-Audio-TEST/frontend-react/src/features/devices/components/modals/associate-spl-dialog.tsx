/**
 * 播放设备关联声压映射弹窗（16_设备域.md §6.4；Dialog sm:max-w-md）。
 * 标题「关联声压映射」；映射 Select（GET /spl 真实选项「{名}（已校准/未校准）」，ui 基元）+
 * 主钮「关联」调 POST /playback-devices/{id}/associate-spl（INT-721 接线）；
 * 校验：必选拦截 + 后端 400（映射 device/device_type 不匹配）经 ApiError.userMessage 内联展示。
 * P3-26 返修：手写原生 select → ui Select。
 */
import { AudioLines, Check } from 'lucide-react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { AssociateSplState } from '@/features/devices/types'
import { useAssociateSplMutation } from '@/application/devices/use-devices'
import { useSplMappingsByDevice } from '@/application/spl/useSplMappings'
import { ApiError } from '@/infrastructure/api/api-error'

export function AssociateSplDialog({
  state,
  onOpenChange,
}: {
  state: AssociateSplState
  onOpenChange: (open: boolean) => void
}) {
  const [mappingId, setMappingId] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const deviceId = state.open ? state.device?.id ?? null : null
  const splQuery = useSplMappingsByDevice(deviceId)
  const { associate } = useAssociateSplMutation()
  const splOptions = splQuery.data ?? []

  useEffect(() => {
    if (state.open) {
      setMappingId('')
      setError(null)
    }
  }, [state.open])

  const handleAssociate = async () => {
    if (!mappingId) {
      setError('请选择一个声压映射')
      return
    }
    if (!state.device) return
    setSubmitting(true)
    setError(null)
    try {
      await associate.mutateAsync({ deviceId: state.device.id, splMappingId: Number(mappingId) })
      toast.success('SPL 映射关联成功')
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : '关联失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={state.open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>关联声压映射</DialogTitle>
          <DialogDescription>
            为播放设备「{state.device?.name ?? ''}」选择关联的增益映射。
          </DialogDescription>
        </DialogHeader>

        <div className='flex flex-col gap-2'>
          <div className='flex items-center gap-2'>
            <AudioLines aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
            <Select value={mappingId} onValueChange={(value) => { setMappingId(value ?? ''); setError(null) }}>
              <SelectTrigger
                size='sm'
                className={cn('w-full', error && 'border-destructive')}
                aria-label='选择声压映射'
              >
                <SelectValue placeholder='请选择声压映射' />
              </SelectTrigger>
              <SelectContent>
                {splOptions.map((mapping) => (
                  <SelectItem key={mapping.id} value={String(mapping.id)}>
                    {mapping.name}（{mapping.calibrationStatus === 'calibrated' ? '已校准' : '未校准'}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {error && <p className='text-destructive text-xs'>{error}</p>}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={submitting} onClick={() => void handleAssociate()}>
            <Check aria-hidden='true' className='size-3.5' />
            {submitting ? '关联中...' : '关联'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
