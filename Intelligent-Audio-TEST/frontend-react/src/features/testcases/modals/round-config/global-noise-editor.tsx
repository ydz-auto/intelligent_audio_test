/**
 * 全局背景噪声编辑器（11_用例域.md §5.1.3.2；INT-1424 按负责人口径恢复为用例配置
 * 独立节，不再嵌在「评估策略」折叠节内；全真数据无 mock）。
 * 受控组件（value/onChange），作用例级 config.background_noise 字段编辑器。
 * 未配置空态「未配置全局背景噪声，点击"添加全局噪声"开始配置」+「+ 添加全局噪声」ghost 钮
 * （已配置则钮位换「移除」destructive 软钮）；噪声音频卡（文件名+时长+标签 chips+更换/试听
 * ——试听走真实音频流，AudioPreviewConfigDialog）；声压级 dB number 0-120 step 1；
 * 循环播放 Switch；逻辑音箱 chips 多选（GET /playback-devices/speaker-groups；用例只关联逻辑音箱，
 * 实体设备由执行/试听时按实验室换绑）。
 * 数据契约 TestCaseBackgroundNoiseItem { audio_id, audio_name?, audio?, spl,
 *   playback_speaker_group_ids[]（新）/ device_ids[]（历史）, loop }。
 */
import { AudioWaveform, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type {
  TestCaseBackgroundNoiseItem,
} from '@/domain/models/evaluationStrategy'
import { usePlaybackSpeakerGroups } from '@/application/devices/use-devices'
import { AudioSelectDialog } from '@/features/testcases/modals/audio/audio-select-dialog'
import {
  AudioPreviewConfigDialog,
  type PreviewAudioItem,
} from '@/features/testcases/modals/audio-preview-config-dialog'

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
  const groupsQuery = usePlaybackSpeakerGroups()
  /** 逻辑音箱（chips 多选数据源；用例只关联逻辑音箱） */
  const groups = useMemo(() => groupsQuery.data ?? [], [groupsQuery.data])
  const [selectingAudio, setSelectingAudio] = useState(false)
  /** 试听对象（INT-1424：试听 → 真实音频试听配置弹窗，实验室由弹窗选择） */
  const [previewItem, setPreviewItem] = useState<PreviewAudioItem | null>(null)
  const configured = value != null

  const selectedGroupIds = (value?.speakerGroupIds ?? []).map(String)

  const toggleGroup = (id: string) =>
    onChange({
      ...value,
      speakerGroupIds: (() => {
        const next = new Set(selectedGroupIds)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return [...next].map((v) => Number(v))
      })(),
    })

  /** 试听逻辑音箱标签（已选组 id → 名称） */
  const previewDeviceLabels = useMemo(
    () =>
      selectedGroupIds
        .map((id) => groups.find((group) => String(group.id) === id))
        .filter((group): group is NonNullable<typeof group> => group != null)
        .map((group) => `[逻辑音箱] ${group.name}`),
    [selectedGroupIds, groups]
  )

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
            {value?.audioId != null && (
              <Button
                type='button'
                variant='ghost'
                size='sm'
                className='h-7'
                onClick={() =>
                  setPreviewItem({
                    id: value.audioId as number | string,
                    name: value?.audioName ?? value?.audio?.name ?? null,
                    spl: value?.spl ?? 0,
                    // 音频库时长兜底：实验室播放无浏览器流，播放器总时长靠它（INT-1424 UX 复核）
                    duration: value?.audio?.duration ?? null,
                    deviceLabels: previewDeviceLabels,
                    // 实验室试听必须先选实验室，由试听弹窗把逻辑音箱解析成实体设备
                    speakerGroupIds: selectedGroupIds,
                  })
                }
              >
                试听
              </Button>
            )}
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

          {/* 逻辑音箱（可多选）chips（GET /playback-devices/speaker-groups） */}
          <div className='space-y-1.5'>
            <Label className='text-sm'>逻辑音箱（可多选）</Label>
            <div className='flex flex-wrap gap-1.5'>
              {groups.length === 0 && (
                <p className='text-muted-foreground/70 text-xs'>暂无可用的逻辑音箱</p>
              )}
              {groups.map((group) => {
                const checked = selectedGroupIds.includes(String(group.id))
                return (
                  <button
                    key={group.id}
                    type='button'
                    aria-pressed={checked}
                    onClick={() => toggleGroup(String(group.id))}
                    className={cn(
                      'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                      checked
                        ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                        : 'hover:bg-accent border-border text-muted-foreground'
                    )}
                  >
                    [逻辑音箱] {group.name}
                  </button>
                )
              })}
            </div>
            <p className='text-muted-foreground/70 text-xs'>
              留空表示不指定播放目标；执行时按执行实验室换成本实验室的实体音箱。
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

      {/* 试听配置弹窗（真实音频流） */}
      <AudioPreviewConfigDialog
        open={previewItem != null}
        onOpenChange={(open) => !open && setPreviewItem(null)}
        caseItem={null}
        audioItem={previewItem}
      />
    </div>
  )
}
