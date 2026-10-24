/**
 * 批量设备面板（11_用例域.md §5.1 音频列表工具栏「批量设备」）。
 * 弹批量设置播放设备面板（设备 Select「{设备名} (通道 {n}) [干声/噪声]」），
 * 应用到当前轮次音频列表全部/勾选音频。
 */
import { useState } from 'react'

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
import type { BatchScope } from '@/domain/lib/audio-batch-ops'
import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'

export function BatchDevicePanel({
  open,
  onOpenChange,
  devices,
  selectedCount,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  devices: PlaybackDeviceOption[]
  /** 当前勾选音频数（0 时「勾选音频」项禁用） */
  selectedCount: number
  onConfirm: (deviceId: string, scope: BatchScope) => void
}) {
  const [deviceId, setDeviceId] = useState('')
  const [scope, setScope] = useState<BatchScope>('all')

  // 声明式 items：闭合态取 label，否则 base-ui 回退显示设备 id（INT-1686）
  const deviceItems = devices.map((d) => ({
    value: d.id,
    label: `${d.name} (通道 ${d.channel}) [${d.type}]`,
  }))

  const confirm = () => {
    if (!deviceId) return
    onConfirm(deviceId, scope)
    setDeviceId('')
    setScope('all')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>批量设置播放设备</DialogTitle>
          <DialogDescription>应用到当前轮次音频列表（全部或勾选）</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>播放设备</span>
            <Select
              value={deviceId}
              onValueChange={(v) => setDeviceId(v ?? '')}
              items={deviceItems}
            >
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择设备' />
              </SelectTrigger>
              <SelectContent>
                {deviceItems.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>应用范围</span>
            <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
              <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
                <input type='radio' name='batch-device-scope' checked={scope === 'all'} onChange={() => setScope('all')} />
                全部音频
              </label>
              <label
                className={
                  selectedCount > 0
                    ? 'hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
                    : 'text-muted-foreground flex cursor-not-allowed items-center gap-1.5 rounded-md px-2 py-1 text-sm'
                }
              >
                <input
                  type='radio'
                  name='batch-device-scope'
                  checked={scope === 'selected'}
                  disabled={selectedCount === 0}
                  onChange={() => setScope('selected')}
                />
                勾选音频（{selectedCount} 个）
              </label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!deviceId} onClick={confirm}>
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
