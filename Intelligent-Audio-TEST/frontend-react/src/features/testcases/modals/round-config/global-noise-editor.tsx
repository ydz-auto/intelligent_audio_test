/**
 * 全局背景噪声编辑器（11_用例域.md §5.1.3.2 评估策略字段，原 §5.1.1 常驻节移入）。
 * 受控组件（value/onChange），作策略字段编辑器由评估策略节引用复用（GlobalNoiseEditor 不再
 * 是用例常驻节——抽屉瘦身一半，INT-592 口径）。
 * 未配置空态「未配置全局背景噪声，点击"添加全局噪声"开始配置」+「+ 添加全局噪声」ghost 钮
 * （已配置则钮位换「移除」destructive 软钮）；噪声音频卡（文件名+时长+标签 chips+更换/试听）
 * ——点「添加全局噪声/更换」打开音频选择子弹窗（AudioSelectDialog audioType='noise' 单选，
 * 真实 GET /audios 经 infrastructure/api/audioLibraryApi）；声压级 dB number 0-120 step 1；
 * 循环播放 Switch；播放设备 chips 多选（真实 GET /playback-devices，设备名存在但未匹配到 ID
 * 时黄色警示 chip——未匹配判定以真实设备列表为准）。
 * 数据契约 TestCaseBackgroundNoiseItem { audio_id, audio_name?, audio?, spl, device_ids[],
 *   device_names[]?, loop }（schemas/testcase.py:68-82 extra='allow' 兼容）。
 */
import { AudioWaveform, Plus, Trash2, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type {
  TestCaseBackgroundNoiseItem,
} from '@/domain/models/evaluationStrategy'
import { AudioSelectDialog } from '@/features/testcases/modals/audio/audio-select-dialog'
import { playbackDeviceLabel } from '@/features/testcases/modals/round-config/playback-device-label'
import { fetchRealPlaybackDevices } from '@/infrastructure/api/playback-api'

const formatDuration = (s: number | null | undefined) =>
  s == null ? '—' : s < 60 ? `${s}s` : s % 60 === 0 ? `${s / 60}m` : `${Math.floor(s / 60)}m ${s % 60}s`

export function GlobalNoiseEditor({
  value,
  onChange,
}: {
  /** 策略/用例承载字段；null=未配置 */
  value: TestCaseBackgroundNoiseItem | null
  onChange: (next: TestCaseBackgroundNoiseItem | null) => void
}) {
  const [selectingAudio, setSelectingAudio] = useState(false)
  const configured = value != null
  const devicesQuery = useQuery({
    queryKey: ['playback-devices', 'real'],
    queryFn: fetchRealPlaybackDevices,
    staleTime: 30_000,
  })
  const devices = devicesQuery.data ?? []

  const toggleDevice = (id: number | string) =>
    onChange({
      ...value,
      deviceIds: (() => {
        const next = new Set((value?.deviceIds ?? []).map(String))
        if (next.has(String(id))) next.delete(String(id))
        else next.add(String(id))
        return [...next].map((v) => (/^\d+$/.test(v) ? Number(v) : v))
      })(),
    })

  /** 播放设备名存在但未匹配到真实设备列表中的 ID（旧配置残留名；黄色警示 chip） */
  const unmatchedDeviceNames =
    devicesQuery.isLoading || devicesQuery.isError
      ? []
      : (value?.deviceNames?.filter((name) => !devices.some((d) => d.name === name)) ?? [])

  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-between gap-2'>
        <div>
          <h4 className='text-sm font-medium'>全局背景噪声</h4>
          <p className='text-muted-foreground mt-0.5 text-xs'>
            配置后跨所有轮次持续播放，优先于轮次级噪声
          </p>
        </div>
        {configured ? (
          <Button
            type='button'
            variant='ghost'
            size='sm'
            className='h-7 gap-1 text-destructive hover:text-destructive'
            onClick={() => onChange(null)}
          >
            <Trash2 aria-hidden='true' className='size-3.5' />
            移除
          </Button>
        ) : (
          <Button
            type='button'
            variant='ghost'
            size='sm'
            className='h-7 gap-1'
            onClick={() => setSelectingAudio(true)}
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加全局噪声
          </Button>
        )}
      </div>

      {!configured ? (
        <div className='border-border/60 rounded-lg border border-dashed px-3 py-4 text-center'>
          <p className='text-muted-foreground text-sm'>
            未配置全局背景噪声，点击&quot;添加全局噪声&quot;开始配置
          </p>
        </div>
      ) : (
        <div className='space-y-3'>
          {/* 噪声音频卡（文件名 + 时长 + 标签 chips + 更换/试听） */}
          <div className='bg-background ring-foreground/10 flex flex-wrap items-center gap-3 rounded-lg p-3 ring-1'>
            <AudioWaveform aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
            <span className='min-w-0 flex-1 truncate text-sm'>
              {value?.audioName ?? value?.audio?.name ?? '—'}
            </span>
            {value?.audio?.duration != null && (
              <Badge
                variant='outline'
                className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'
              >
                {formatDuration(value.audio.duration)}
              </Badge>
            )}
            {(value?.audio?.tags ?? []).map((t) => (
              <Badge key={t} variant='secondary' className='rounded-md px-1.5'>
                {t}
              </Badge>
            ))}
            <Button
              type='button'
              variant='ghost'
              size='sm'
              className='h-7'
              onClick={() => setSelectingAudio(true)}
            >
              更换
            </Button>
            <Button
              type='button'
              variant='ghost'
              size='sm'
              className='h-7'
              onClick={() => toast.success(`正在试听：${value?.audioName ?? '音频'}（演示）`)}
            >
              试听
            </Button>
          </div>

          <div className='grid gap-x-6 gap-y-3 sm:grid-cols-2'>
            <div className='space-y-1.5'>
              <Label className='text-sm'>声压级 (dB)</Label>
              <Input
                type='number'
                min={0}
                max={120}
                step={1}
                value={value?.spl ?? 0}
                onChange={(e) => onChange({ ...value, spl: Number(e.target.value) })}
                className='h-8'
              />
            </div>
            <div className='flex items-center gap-2'>
              <Switch
                checked={value?.loop ?? true}
                onCheckedChange={(v) => onChange({ ...value, loop: v })}
                aria-label='循环播放'
                id='global-noise-loop'
              />
              <Label htmlFor='global-noise-loop' className='text-sm font-normal'>
                循环播放
              </Label>
            </div>
          </div>

          {/* 播放设备（可多选）chips —— 真实 GET /playback-devices */}
          <div className='space-y-1.5'>
            <Label className='text-sm'>播放设备（可多选）</Label>
            {devicesQuery.isLoading ? (
              <div className='text-muted-foreground flex h-8 items-center gap-2 text-xs'>
                <Spinner className='size-3.5' />
                加载播放设备...
              </div>
            ) : devicesQuery.isError ? (
              <p className='text-destructive text-xs'>播放设备加载失败，请稍后重试</p>
            ) : (
              <div className='flex flex-wrap gap-1.5'>
                {devices.length === 0 ? (
                  <p className='text-muted-foreground/70 text-xs'>暂无可用的播放设备</p>
                ) : (
                  devices.map((d) => {
                    const checked = (value?.deviceIds ?? [])
                      .map(String)
                      .includes(String(d.id))
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
                        {playbackDeviceLabel(d)}
                      </button>
                    )
                  })
                )}
                {unmatchedDeviceNames.map((name) => (
                  <span
                    key={name}
                    className='flex items-center gap-1 rounded-full border border-yellow-500/50 bg-yellow-500/10 px-2.5 py-1 text-xs text-yellow-700 dark:text-yellow-400'
                  >
                    <TriangleAlert aria-hidden='true' className='size-3.5 shrink-0' />
                    未匹配到播放设备ID：{name}
                  </span>
                ))}
              </div>
            )}
            <p className='text-muted-foreground/70 text-xs'>
              留空表示不指定播放设备；存在旧配置设备名但未匹配到 ID 时显示警示。
            </p>
          </div>
        </div>
      )}

      {/* 音频选择子弹窗（noise 单选） */}
      <AudioSelectDialog
        open={selectingAudio}
        onOpenChange={setSelectingAudio}
        mode='single'
        audioType='noise'
        title='选择噪声音频'
        initialSelected={value?.audioId != null ? [{ id: value.audioId }] : []}
        onConfirm={(selected) => {
          const audio = selected[0]
          if (!audio) return
          onChange({
            ...value,
            audioId: audio.id,
            audioName: audio.name,
            audio: {
              id: audio.id,
              name: audio.name,
              duration: audio.duration,
              tags: audio.tags ?? [],
            },
          })
        }}
      />
    </div>
  )
}
