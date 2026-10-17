/**
 * 批量设置播放设备弹窗（11_用例域.md §5.3.2，Dialog sm:max-w-lg）。
 * 「重新扫描」ghost 钮（扫描中 Spinner「正在扫描可用设备...」，失败红字）+ 播放设备* Select
 * （「{设备名} (通道 {n}) [干声/噪声]」，空态「暂无可用的播放设备」）+ 轮次范围三档
 * （所有轮次统一/指定轮次统一/逐轮设置每轮可不同，§5.3.5 口径）+ 应用层级多选。
 * mock 扫描演示：每次重扫在成功/失败间轮换，失败态红字 + 设备清空（空态可走查）；
 * 数据契约 deviceId/roundMode/rounds/appliedLayers 留接线批次。
 */
import { useEffect, useRef, useState } from 'react'
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
import { Spinner } from '@/components/ui/spinner'
import {
  ApplyLayerField,
  createRoundScope,
  RoundScopeThreeField,
  usePerRoundValue,
} from '@/features/testcases/modals/batch-shared'

/** mock 可用播放设备（§5.3.2「{设备名} (通道 {n}) [干声/噪声]」口径） */
const MOCK_SCAN_DEVICES = [
  { id: 'dev-1', name: '音频接口 A', channel: 1, type: '干声' },
  { id: 'dev-2', name: '音频接口 B', channel: 2, type: '噪声' },
  { id: 'dev-3', name: '功放 左声道', channel: 1, type: '干声' },
  { id: 'dev-4', name: '功放 右声道', channel: 2, type: '噪声' },
  { id: 'dev-5', name: '实验室喇叭组', channel: 3, type: '干声' },
]

type ScanState = 'ready' | 'scanning' | 'error'

export function BatchDeviceDialog({
  open,
  onOpenChange,
  count,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
}) {
  const [scanState, setScanState] = useState<ScanState>('ready')
  const [scanRound, setScanRound] = useState(0)
  const timerRef = useRef<number | null>(null)
  const [scope, setScope] = useState(createRoundScope())
  const { current: deviceId, setCurrent: setDeviceId } = usePerRoundValue('', scope)

  useEffect(() => () => {
    if (timerRef.current != null) window.clearTimeout(timerRef.current)
  }, [])

  const rescan = () => {
    if (scanState === 'scanning') return
    const round = scanRound + 1
    setScanRound(round)
    setScanState('scanning')
    setDeviceId('')
    timerRef.current = window.setTimeout(() => {
      // mock：单数重扫走失败态（红字 + 空设备表），双数恢复成功态
      if (round % 2 === 1) {
        setScanState('error')
      } else {
        setScanState('ready')
      }
    }, 1000)
  }

  const available = scanState === 'ready'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>批量设置播放设备</DialogTitle>
          <DialogDescription>
            您勾选了 {count} 个用例，将统一设置其播放设备
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>
              {scope.mode === 'per_round' ? `第 ${scope.activeRound} 轮播放设备 *` : '播放设备 *'}
            </span>
            <Select
              value={deviceId}
              onValueChange={(v) => setDeviceId(v ?? '')}
              disabled={!available}
            >
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='暂无可用的播放设备' />
              </SelectTrigger>
              <SelectContent>
                {MOCK_SCAN_DEVICES.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name} (通道 {d.channel}) [{d.type}]
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className='flex items-center gap-3'>
              <Button type='button' variant='ghost' size='sm' className='h-7' onClick={rescan}>
                重新扫描
              </Button>
              {scanState === 'scanning' && (
                <span className='text-muted-foreground inline-flex items-center gap-1.5 text-xs'>
                  <Spinner className='size-3.5' />
                  正在扫描可用设备...
                </span>
              )}
              {scanState === 'error' && (
                <span className='text-destructive text-xs'>
                  扫描失败：无法连接设备管理器，请确认实验室设备在线后重试
                </span>
              )}
            </div>
          </div>

          <RoundScopeThreeField
            name='batch-device-round'
            value={scope}
            onChange={setScope}
          />
          <ApplyLayerField />
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
