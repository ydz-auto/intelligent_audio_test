/**
 * 设备交叉面板（11_用例域.md §5.1 音频列表工具栏「设备交叉」）。
 * 多选设备 chips 后确认，按当前音频列表顺序将所选设备轮转分配。
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
import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'

export function CrossDevicePanel({
  open,
  onOpenChange,
  devices,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  devices: PlaybackDeviceOption[]
  /** 确认：按顺序参与轮转的设备 id 列表 */
  onConfirm: (deviceIds: string[]) => void
}) {
  const [selected, setSelected] = useState<string[]>([])

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id]))

  const confirm = () => {
    if (selected.length === 0) return
    onConfirm(selected)
    setSelected([])
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>设备交叉</DialogTitle>
          <DialogDescription>
            多选播放设备后，按当前音频列表顺序轮转分配
          </DialogDescription>
        </DialogHeader>
        <div className='flex flex-wrap gap-1.5'>
          {devices.map((d) => {
            const active = selected.includes(d.id)
            return (
              <button
                key={d.id}
                type='button'
                aria-pressed={active}
                onClick={() => toggle(d.id)}
                className={
                  active
                    ? 'bg-primary text-primary-foreground rounded-md px-2 py-1 text-sm transition-colors'
                    : 'hover:bg-accent rounded-md border px-2 py-1 text-sm transition-colors'
                }
              >
                {d.name} (通道 {d.channel}) [{d.type}]
              </button>
            )
          })}
        </div>
        <p className='text-muted-foreground text-xs'>
          已选 {selected.length} 个设备
          {selected.length === 0 && '（至少选择 1 个）'}
        </p>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={selected.length === 0} onClick={confirm}>
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
