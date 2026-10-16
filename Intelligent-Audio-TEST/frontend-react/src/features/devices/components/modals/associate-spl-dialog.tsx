/**
 * 播放设备关联声压映射弹窗（16_设备域.md §6.4；Dialog sm:max-w-md）。
 * 标题「关联声压映射」；映射 Select（GET /spl/by-device/{id}，选项「{名}（已校准/未校准）」，ui 基元）+
 * 校验提示（映射 device_id/device_type 不匹配后端 400 内联展示 §9「SPL 映射类型不匹配：
 * 映射类型为 {a}, 设备类型为 {b}」）；主钮「关联」（playback:control）；成功 toast「SPL 映射关联成功」。
 * P3-26 返修：手写原生 select → ui Select；错误文案对齐 §9。
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
import { PLAYBACK_DEVICE_TYPE_META } from '@/domain/models/playbackDevice'

/** 可选 SPL 映射 refs（§6.4 选项「{名}（已校准）」；mock 阶段静态） */
export const MOCK_ASSOCIATE_SPL_OPTIONS = [
  { id: 1, name: 'ASR-65dB-标准校准', calibrationStatus: 'calibrated' },
  { id: 2, name: 'WS-70dB-高增益校准', calibrationStatus: 'calibrated' },
  { id: 3, name: 'REF-192k-高采样校准', calibrationStatus: 'uncalibrated' },
]

export function AssociateSplDialog({
  state,
  onOpenChange,
}: {
  state: AssociateSplState
  onOpenChange: (open: boolean) => void
}) {
  const [mappingId, setMappingId] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (state.open) {
      setMappingId('')
      setError(null)
    }
  }, [state.open])

  const handleAssociate = () => {
    if (!mappingId) {
      setError('请选择一个声压映射')
      return
    }
    const mapping = MOCK_ASSOCIATE_SPL_OPTIONS.find((m) => m.id === Number(mappingId))
    if (mapping && mapping.calibrationStatus === 'uncalibrated') {
      const deviceType = state.device?.deviceType
      const deviceTypeLabel = deviceType ? (PLAYBACK_DEVICE_TYPE_META[deviceType]?.label ?? deviceType) : '未知'
      // §9 文案：SPL 映射类型不匹配：映射类型为 {a}, 设备类型为 {b}
      setError(`SPL 映射类型不匹配：映射类型为「${mapping.name}」, 设备类型为「${deviceTypeLabel}」`)
      return
    }
    setError(null)
    toast.success('SPL 映射关联成功')
    onOpenChange(false)
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
                {MOCK_ASSOCIATE_SPL_OPTIONS.map((mapping) => (
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
          <Button onClick={handleAssociate}>
            <Check aria-hidden='true' className='size-3.5' />
            关联
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
