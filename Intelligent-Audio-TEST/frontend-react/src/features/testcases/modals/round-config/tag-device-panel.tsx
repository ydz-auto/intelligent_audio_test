/**
 * 标签设备面板（11_用例域.md §5.1 音频列表工具栏「标签设备」，新增工具栏项）。
 * 标签→设备映射面板：选标签 → 选目标播放设备 → 应用到该标签命中的音频（批量设置播放设备）。
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
import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'

export function TagDevicePanel({
  open,
  onOpenChange,
  tags,
  devices,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 可选标签源（mock 标签源 MOCK_TAGS） */
  tags: string[]
  devices: PlaybackDeviceOption[]
  /** 确认：标签 → 目标设备 */
  onConfirm: (tag: string, deviceId: string) => void
}) {
  const [tag, setTag] = useState('')
  const [deviceId, setDeviceId] = useState('')

  // 声明式 items：闭合态取 label，否则 base-ui 回退显示设备 id（INT-1686）
  const deviceItems = devices.map((d) => ({
    value: d.id,
    label: `${d.name} (通道 ${d.channel}) [${d.type}]`,
  }))

  const confirm = () => {
    if (!tag || !deviceId) return
    onConfirm(tag, deviceId)
    setTag('')
    setDeviceId('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>标签设备</DialogTitle>
          <DialogDescription>
            选择标签与目标播放设备，将该标签命中的音频播放设备批量设置
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-3 sm:grid-cols-2'>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>标签</span>
            <Select value={tag} onValueChange={(v) => setTag(v ?? '')}>
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择标签' />
              </SelectTrigger>
              <SelectContent>
                {tags.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>目标播放设备</span>
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
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!tag || !deviceId} onClick={confirm}>
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
