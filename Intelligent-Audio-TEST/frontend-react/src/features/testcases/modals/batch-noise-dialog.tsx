/**
 * 批量设置噪声弹窗（11_用例域.md §5.3.4，Dialog sm:max-w-xl）。
 * 噪声音频（选择器卡「点击选择噪声音频」→ 打开音频选择弹窗；已选显名 + 重新选择/清除）
 * + 噪声声压级 dB（number 0-140，提示「建议值：94 dB（1kHz 校准点）」）
 * + 播放设备（多选选择器卡）+ 轮次范围三档（所有轮次统一/指定轮次统一/逐轮设置每轮可不同，
 * §5.3.5 口径）+ 应用层级多选（默认勾选 case级/segment级背景噪声）。
 * 可视稿演示态：提交走 toast；数据契约 noiseAudio/spl/deviceIds/roundMode/rounds/appliedLayers 留接线批次。
 */
import { AudioWaveform } from 'lucide-react'
import { useState } from 'react'
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
import { cn } from '@/lib/utils'
import {
  ApplyLayerField,
  createRoundScope,
  RoundScopeThreeField,
  usePerRoundValue,
} from '@/features/testcases/modals/batch-shared'

/** mock 噪声音频（§5.3.4 音频选择弹窗，audioType='noise' 单选；形态对齐 AudioAsset 简版） */
const MOCK_NOISE_AUDIOS = [
  { id: 'au-n1', name: '粉红噪声_94dB.wav', duration: 180, tags: ['粉红噪声'] },
  { id: 'au-n2', name: '白噪声_85dB.wav', duration: 120, tags: ['白噪声'] },
  { id: 'au-n3', name: '音乐背景_闹钟.wav', duration: 18, tags: ['音乐背景', '闹钟'] },
  { id: 'au-n4', name: '街道环境音.wav', duration: 240, tags: ['街道', '环境'] },
]

type NoiseAudio = (typeof MOCK_NOISE_AUDIOS)[number]

/** 单轮噪声配置值（逐轮设置时每轮一份；统一/指定轮次共用一份） */
type NoiseValue = {
  audio: NoiseAudio | null
  spl: string
  devices: Set<string>
}

/** mock 播放设备（§5.3.4 多选选择器卡） */
const MOCK_PLAYBACK_DEVICES = [
  { id: 'dev-1', name: '音频接口 A', channel: 1, type: '干声' },
  { id: 'dev-2', name: '音频接口 B', channel: 2, type: '噪声' },
  { id: 'dev-3', name: '功放 左声道', channel: 1, type: '干声' },
  { id: 'dev-4', name: '功放 右声道', channel: 2, type: '噪声' },
]

const formatDuration = (s: number) =>
  s < 60 ? `${s}s` : s % 60 === 0 ? `${s / 60}m` : `${Math.floor(s / 60)}m ${s % 60}s`

/** 音频选择子弹窗（嵌套 Dialog；选择即回调并关闭） */
function NoiseAudioPickerDialog({
  open,
  onOpenChange,
  onSelect,
  currentId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (audio: NoiseAudio) => void
  currentId: string | null
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>选择噪声音频</DialogTitle>
          <DialogDescription>
            选择一个噪声音频文件作为所选用例的背景噪声
          </DialogDescription>
        </DialogHeader>
        <div className='space-y-1.5'>
          {MOCK_NOISE_AUDIOS.map((a) => {
            const selected = currentId === a.id
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
                {a.tags.map((t) => (
                  <Badge key={t} variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                    {t}
                  </Badge>
                ))}
              </button>
            )
          })}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function BatchNoiseDialog({
  open,
  onOpenChange,
  count,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
}) {
  const [scope, setScope] = useState(createRoundScope())
  const [pickingAudio, setPickingAudio] = useState(false)
  const { current: noise, setCurrent: setNoise } = usePerRoundValue<NoiseValue>(
    { audio: null, spl: '94', devices: new Set(['dev-1', 'dev-3']) },
    scope
  )

  const setAudio = (audio: NoiseAudio | null) => setNoise({ ...noise, audio })
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
                {audio.tags.map((t) => (
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
              {MOCK_PLAYBACK_DEVICES.map((d) => {
                const checked = deviceIds.has(d.id)
                return (
                  <button
                    key={d.id}
                    type='button'
                    aria-pressed={checked}
                    onClick={() => toggleDevice(d.id)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                      checked
                        ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                        : 'hover:bg-accent border-border text-muted-foreground'
                    )}
                  >
                    {d.name} (通道 {d.channel}) [{d.type}]
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
          />

          {/* 应用层级（默认勾选 case级/segment级背景噪声） */}
          <ApplyLayerField defaultChecked={['case-bg', 'segment-bg']} />
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

      <NoiseAudioPickerDialog
        open={pickingAudio}
        onOpenChange={setPickingAudio}
        currentId={audio?.id ?? null}
        onSelect={(a) => setAudio(a)}
      />
    </Dialog>
  )
}
