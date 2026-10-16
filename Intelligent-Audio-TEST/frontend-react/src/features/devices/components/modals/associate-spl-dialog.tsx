/**
 * 播放设备关联声压映射弹窗（16_设备域.md §6.4；Dialog sm:max-w-md）。
 * 标题「关联声压映射」；映射 Select（GET /spl/by-device/{id}，选项「{名}（已校准/未校准）」）+
 * 校验提示（映射 device_id/device_type 不匹配后端 400 内联展示「SPL 映射设备不匹配/类型不匹配」）；
 * 主钮「关联」（playback:control）；成功 toast「SPL 映射关联成功」。
 */
import { AudioLines, Check, ChevronDown } from 'lucide-react'
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
import { cn } from '@/lib/utils'
import type { AssociateSplState } from '@/features/devices/types'

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
  const [mappingId, setMappingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (state.open) {
      setMappingId(null)
      setError(null)
    }
  }, [state.open])

  const handleAssociate = () => {
    if (mappingId == null) {
      setError('请选择一个声压映射')
      return
    }
    const mapping = MOCK_ASSOCIATE_SPL_OPTIONS.find((m) => m.id === mappingId)
    if (mapping && mapping.calibrationStatus === 'uncalibrated') {
      setError('SPL 映射类型不匹配：映射类型为设备 SPL，请选择已校准映射')
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
          <div className='relative'>
            <AudioLines aria-hidden='true' className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2' />
            <select
              value={mappingId ?? ''}
              onChange={(e) => {
                setMappingId(e.target.value ? Number(e.target.value) : null)
                setError(null)
              }}
              className={cn(
                'border-input h-9 w-full appearance-none rounded-lg border bg-transparent ps-7 pr-8 text-sm outline-none',
                error && 'border-destructive'
              )}
              aria-label='选择声压映射'
            >
              <option value=''>请选择声压映射</option>
              {MOCK_ASSOCIATE_SPL_OPTIONS.map((mapping) => (
                <option key={mapping.id} value={mapping.id}>
                  {mapping.name}（{mapping.calibrationStatus === 'calibrated' ? '已校准' : '未校准'}）
                </option>
              ))}
            </select>
            <ChevronDown aria-hidden='true' className='text-muted-foreground pointer-events-none absolute end-2 top-1/2 size-3.5 -translate-y-1/2' />
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
