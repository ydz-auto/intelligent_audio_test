/**
 * 批量设置噪声弹窗（11_用例域.md §5.3.4，Dialog sm:max-w-xl；INT-710 真实数据接线）。
 * 噪声音频（选择器卡「点击选择噪声音频」→ 打开音频选择弹窗，真实 GET /audios audio_type=noise；
 * 已选显名 + 重新选择/清除）+ 噪声声压级 dB（number 0-140，提示「建议值：94 dB（1kHz 校准点）」）
 * + 播放设备（多选选择器卡，真实 GET /playback-devices）+ 轮次范围三档 + 应用层级多选
 * （默认勾选 case级/segment级背景噪声）。
 * 提交走 POST /testcases/batch（update_noise）：noise_audio_id/noise_spl/noise_device_ids
 * + targets + round_mode/round_numbers。
 */
import { AudioWaveform } from 'lucide-react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
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
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import type { AudioAsset } from '@/domain/models/audio'
import { fetchRealAudios } from '@/infrastructure/api/audio-list-api'
import { fetchRealPlaybackDevices } from '@/infrastructure/api/playback-api'
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

const formatDuration = (s: number | null) => {
  if (s == null) return '—'
  return s < 60 ? `${s}s` : s % 60 === 0 ? `${s / 60}m` : `${Math.floor(s / 60)}m ${s % 60}s`
}

/** 单轮噪声配置值（逐轮设置时每轮一份；统一/指定轮次共用一份） */
type NoiseValue = {
  audio: AudioAsset | null
  spl: string
  devices: Set<string>
}

/** 音频选择子弹窗（嵌套 Dialog；选择即回调并关闭） */
function NoiseAudioPickerDialog({
  open,
  onOpenChange,
  onSelect,
  currentId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (audio: AudioAsset) => void
  currentId: string | null
}) {
  const audiosQuery = useQuery({
    queryKey: ['audios', 'real', 'noise'],
    queryFn: () => fetchRealAudios({ audioType: 'noise', perPage: 200 }),
    staleTime: 30_000,
    enabled: open,
  })
  const audios = audiosQuery.data?.items ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>选择噪声音频</DialogTitle>
          <DialogDescription>
            选择一个噪声音频文件作为所选用例的背景噪声
          </DialogDescription>
        </DialogHeader>
        {audiosQuery.isLoading ? (
          <div className='flex h-24 items-center justify-center gap-2 text-sm text-muted-foreground'>
            <Spinner className='size-4' />
            正在加载噪声音频...
          </div>
        ) : audiosQuery.isError ? (
          <div className='px-3 py-6 text-center'>
            <p className='text-destructive text-sm'>加载噪声音频失败</p>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='mt-2 h-7'
              onClick={() => void audiosQuery.refetch()}
            >
              重试
            </Button>
          </div>
        ) : audios.length === 0 ? (
          <p className='text-muted-foreground px-3 py-6 text-center text-sm'>
            暂无可用的噪声音频
          </p>
        ) : (
          <div className='space-y-1.5'>
            {audios.map((a) => {
              const selected = currentId === String(a.id)
              return (
                <button
                  key={a.id}
                  type='button'
                  className={cn(
                    'hover:bg-accent flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-start text-sm transition-colors',
                    selected && 'bg-primary/10 border-primary/40'
                  )}
                  onClick={() => {
                    onSelect(a)
                    onOpenChange(false)
                  }}
                >
                  <AudioWaveform
                    aria-hidden='true'
                    className='text-muted-foreground size-4 shrink-0'
                  />
                  <span className='min-w-0 flex-1 truncate'>{a.name}</span>
                  <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                    {formatDuration(a.duration)}
                  </span>
                  {a.tags.slice(0, 2).map((t) => (
                    <Badge key={t} variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                      {t}
                    </Badge>
                  ))}
                </button>
              )
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function BatchNoiseDialog({
  open,
  onOpenChange,
  count,
  ids,
  roundCount,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
  /** 选中用例实际轮次数（config.rounds 派生；0=空态） */
  roundCount: number
}) {
  const [scope, setScope] = useState(() => createRoundScope(roundCount))
  const [pickingAudio, setPickingAudio] = useState(false)
  const [layers, setLayers] = useState<ApplyLayerId[]>(['case-bg', 'segment-bg'])
  const [submitting, setSubmitting] = useState(false)
  const {
    current: noise,
    setCurrent: setNoise,
    perRound,
  } = usePerRoundValue<NoiseValue>(
    { audio: null, spl: '94', devices: new Set() },
    scope
  )

  const devicesQuery = useQuery({
    queryKey: ['playback-devices', 'real'],
    queryFn: fetchRealPlaybackDevices,
    staleTime: 30_000,
    enabled: open,
  })
  const devices = devicesQuery.data ?? []

  const setAudio = (audio: AudioAsset | null) => setNoise({ ...noise, audio })
  const setSpl = (spl: string) => setNoise({ ...noise, spl })
  const toggleDevice = (id: string) =>
    setNoise({
      ...noise,
      devices: (() => {
        const next = new Set(noise.devices)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })(),
    })

  const audio = noise.audio
  const spl = noise.spl
  const deviceIds = noise.devices

  const handleSubmit = async () => {
    const targets = applyLayerToTargets(layers)
    let payload: TestcaseBatchPayload
    if (scope.mode === 'per_round') {
      // 逐轮设置：round_values = {轮次号: {audioId, spl, deviceIds, targets}}，仅含用户实际编辑过的轮次
      const roundValues: Record<string, unknown> = {}
      for (const [roundKey, nv] of Object.entries(perRound)) {
        if (!nv.audio) continue
        const roundSpl = Number(nv.spl)
        if (Number.isNaN(roundSpl)) continue
        roundValues[roundKey] = {
          audioId: nv.audio.id,
          spl: roundSpl,
          deviceIds: [...nv.devices]
            .map((id) => Number(id))
            .filter((n) => !Number.isNaN(n)),
          targets,
        }
      }
      if (Object.keys(roundValues).length === 0) {
        toast.error('请至少为一个轮次选择噪声音频')
        return
      }
      payload = { roundMode: 'per_round', roundNumbers: [], roundValues }
    } else {
      const splValue = Number(spl)
      if (!audio || Number.isNaN(splValue)) return
      payload = {
        noiseAudioId: audio.id,
        noiseSpl: splValue,
        noiseDeviceIds: [...deviceIds]
          .map((id) => Number(id))
          .filter((n) => !Number.isNaN(n)),
        targets,
        roundMode: scope.mode as TestcaseRoundMode,
        roundNumbers:
          scope.mode === 'specific' ? scope.specificRounds : undefined,
      }
    }
    setSubmitting(true)
    try {
      await batchTestcaseAction('update_noise', ids, payload)
      toast.success(`批量操作执行成功（更新 ${count} 个）`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量设置噪声失败')
    } finally {
      setSubmitting(false)
    }
  }

  /** 逐轮模式：任一编辑过的轮次已选噪声音频即可提交 */
  const canSubmit =
    scope.mode === 'per_round'
      ? Object.values(perRound).some((nv) => nv.audio != null)
      : Boolean(audio) && !Number.isNaN(Number(spl))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>批量设置噪声</DialogTitle>
          <DialogDescription>
            您勾选了 {count} 个用例，将统一设置其噪声
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 噪声音频选择器卡 */}
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>噪声音频</span>
            {audio ? (
              <div className='bg-background ring-foreground/10 flex flex-wrap items-center gap-3 rounded-lg p-3 ring-1'>
                <AudioWaveform
                  aria-hidden='true'
                  className='text-muted-foreground size-4 shrink-0'
                />
                <span className='min-w-0 flex-1 truncate text-sm'>{audio.name}</span>
                <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                  {formatDuration(audio.duration)}
                </span>
                {audio.tags.slice(0, 2).map((t) => (
                  <Badge key={t} variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                    {t}
                  </Badge>
                ))}
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  className='h-7'
                  onClick={() => setPickingAudio(true)}
                >
                  重新选择
                </Button>
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  className='h-7 hover:text-destructive'
                  onClick={() => setAudio(null)}
                >
                  清除
                </Button>
              </div>
            ) : (
              <button
                type='button'
                onClick={() => setPickingAudio(true)}
                className='border-border/60 hover:bg-accent flex w-full items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-6 text-sm transition-colors'
              >
                <AudioWaveform aria-hidden='true' className='text-muted-foreground size-4' />
                点击选择噪声音频
              </button>
            )}
          </div>

          {/* 噪声声压级 */}
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>
              {scope.mode === 'per_round'
                ? `第 ${scope.activeRound} 轮噪声声压级 dB`
                : '噪声声压级 dB'}
            </span>
            <Input
              type='number'
              min={0}
              max={140}
              value={spl}
              onChange={(e) => setSpl(e.target.value)}
              className='h-8'
              aria-label='噪声声压级 dB'
            />
            <p className='text-muted-foreground/70 text-xs'>
              建议值：94 dB（1kHz 校准点）
            </p>
          </div>

          {/* 播放设备（多选）选择器卡 */}
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>播放设备（可多选）</span>
            <div className='flex flex-wrap gap-1.5'>
              {devices.map((d) => {
                const id = String(d.id)
                const checked = deviceIds.has(id)
                return (
                  <button
                    key={d.id}
                    type='button'
                    aria-pressed={checked}
                    onClick={() => toggleDevice(id)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                      checked
                        ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                        : 'hover:bg-accent border-border text-muted-foreground'
                    )}
                  >
                    {d.name} (通道 {d.channelIndex ?? '—'}) [{d.deviceType === 'dry' ? '干声' : d.deviceType === 'noise' ? '噪声' : d.deviceType ?? '未知'}]
                  </button>
                )
              })}
            </div>
            <p className='text-muted-foreground/70 text-xs'>
              留空表示不指定播放设备
            </p>
          </div>

          <RoundScopeThreeField
            name='batch-noise-round'
            value={scope}
            onChange={setScope}
            roundCount={roundCount}
          />

          {/* 应用层级（默认勾选 case级/segment级背景噪声） */}
          <ApplyLayerField
            defaultChecked={['case-bg', 'segment-bg']}
            value={layers}
            onChange={setLayers}
            hint='可多选；留空时默认应用到 case级/segment级背景噪声'
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={submitting || !canSubmit}
          >
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>

      <NoiseAudioPickerDialog
        open={pickingAudio}
        onOpenChange={setPickingAudio}
        currentId={audio ? String(audio.id) : null}
        onSelect={(a) => setAudio(a)}
      />
    </Dialog>
  )
}
