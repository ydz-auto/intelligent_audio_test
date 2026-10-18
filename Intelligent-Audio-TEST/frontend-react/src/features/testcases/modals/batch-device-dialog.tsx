/**
 * 批量设置播放设备弹窗（11_用例域.md §5.3.2，Dialog sm:max-w-lg；INT-710 真实数据接线）。
 * 「重新扫描」ghost 钮（扫描中 Spinner「正在扫描可用设备...」，失败红字）+ 播放设备* Select
 * （真实 GET /playback-devices「{设备名} (通道 {n}) [干声/噪声]」，空态「暂无可用的播放设备」，
 * POST /playback-devices/scan 重新扫描）+ 轮次范围三档（§3.5 口径）+ 应用层级多选。
 * 提交走 POST /testcases/batch（update_playback_devices）：
 * playback_devices.deviceId + targets + round_mode/round_numbers。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  fetchRealPlaybackDevices,
  scanRealPlaybackDevices,
} from '@/infrastructure/api/playback-api'
import {
  batchTestcaseAction,
  type TestcaseBatchPayload,
  type TestcaseRoundMode,
} from '@/infrastructure/api/testcases-batch-api'
import {
  applyLayerToTargets,
  ApplyLayerField,
  createRoundScope,
  RoundScopeThreeField,
  usePerRoundValue,
  type ApplyLayerId,
} from '@/features/testcases/modals/batch-shared'

type ScanState = 'ready' | 'scanning' | 'error'

export function BatchDeviceDialog({
  open,
  onOpenChange,
  count,
  ids,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
}) {
  const queryClient = useQueryClient()
  const [scanState, setScanState] = useState<ScanState>('ready')
  const [scanError, setScanError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [scope, setScope] = useState(createRoundScope())
  const [layers, setLayers] = useState<ApplyLayerId[]>([])
  const {
    current: deviceId,
    setCurrent: setDeviceId,
    perRound,
  } = usePerRoundValue('', scope)

  const devicesQuery = useQuery({
    queryKey: ['playback-devices', 'real'],
    queryFn: fetchRealPlaybackDevices,
    staleTime: 30_000,
    enabled: open,
  })
  const devices = devicesQuery.data ?? []

  const scanMutation = useMutation({
    mutationFn: scanRealPlaybackDevices,
    onMutate: () => {
      setScanState('scanning')
      setScanError('')
      setDeviceId('')
    },
    onSuccess: (scanned) => {
      setScanState('ready')
      // 扫描到的设备并入列表（照 Vue：按 name|channelIndex 去重追加）
      const existingKeys = new Set(
        devices.map((d) => `${d.name}|${d.channelIndex}`)
      )
      const newDevices = scanned.filter(
        (d) => !existingKeys.has(`${d.name}|${d.channelIndex}`)
      )
      if (newDevices.length > 0) {
        queryClient.setQueryData<typeof devices>(
          ['playback-devices', 'real'],
          (prev) => [...(prev ?? []), ...newDevices]
        )
      }
      toast.success('扫描完成')
    },
    onError: () => {
      setScanState('error')
      setScanError('扫描失败：无法连接设备管理器，请确认实验室设备在线后重试')
    },
  })

  const handleSubmit = async () => {
    const targets = applyLayerToTargets(layers)
    let payload: TestcaseBatchPayload
    if (scope.mode === 'per_round') {
      // 逐轮设置：round_values = {轮次号: {deviceId, targets}}，仅含用户实际编辑过的轮次
      const roundValues: Record<string, unknown> = {}
      for (const [roundKey, roundDeviceId] of Object.entries(perRound)) {
        if (roundDeviceId === '') continue
        const numeric = Number(roundDeviceId)
        if (Number.isNaN(numeric)) continue
        roundValues[roundKey] = { deviceId: numeric, targets }
      }
      if (Object.keys(roundValues).length === 0) {
        toast.error('请至少为一个轮次选择播放设备')
        return
      }
      payload = { roundMode: 'per_round', roundNumbers: [], roundValues }
    } else {
      if (!deviceId) return
      payload = {
        playbackDevices: { deviceId: Number(deviceId) },
        targets,
        roundMode: scope.mode as TestcaseRoundMode,
        roundNumbers:
          scope.mode === 'specific' ? scope.specificRounds : undefined,
      }
    }
    setSubmitting(true)
    try {
      await batchTestcaseAction('update_playback_devices', ids, payload)
      toast.success(`批量操作执行成功（更新 ${count} 个）`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量设置播放设备失败')
    } finally {
      setSubmitting(false)
    }
  }

  /** 逐轮模式：任一编辑过的轮次选了设备即可提交 */
  const canSubmit =
    scope.mode === 'per_round'
      ? Object.values(perRound).some((v) => v !== '')
      : Boolean(deviceId)

  const available = scanState !== 'error'

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
              disabled={!available || devices.length === 0}
            >
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择设备' />
              </SelectTrigger>
              <SelectContent>
                {devices.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.name} (通道 {d.channelIndex ?? '—'}) [{d.deviceType === 'dry' ? '干声' : d.deviceType === 'noise' ? '噪声' : d.deviceType ?? '未知'}]
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {devicesQuery.isLoading ? (
              <p className='text-muted-foreground/70 inline-flex items-center gap-1.5 pt-1 text-xs'>
                <Spinner className='size-3.5' />
                正在加载播放设备...
              </p>
            ) : devices.length === 0 && scanState !== 'scanning' ? (
              <p className='text-muted-foreground/70 pt-1 text-xs'>
                暂无可用的播放设备
              </p>
            ) : null}
            <div className='flex items-center gap-3'>
              <Button
                type='button'
                variant='ghost'
                size='sm'
                className='h-7'
                onClick={() => scanMutation.mutate()}
                disabled={scanMutation.isPending}
              >
                重新扫描
              </Button>
              {scanState === 'scanning' && (
                <span className='text-muted-foreground inline-flex items-center gap-1.5 text-xs'>
                  <Spinner className='size-3.5' />
                  正在扫描可用设备...
                </span>
              )}
              {scanState === 'error' && (
                <span className='text-destructive text-xs'>{scanError}</span>
              )}
            </div>
          </div>

          <RoundScopeThreeField
            name='batch-device-round'
            value={scope}
            onChange={setScope}
          />
          <ApplyLayerField
            value={layers}
            onChange={setLayers}
            hint='可多选；留空时默认应用到目标人音频'
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || !canSubmit}>
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
