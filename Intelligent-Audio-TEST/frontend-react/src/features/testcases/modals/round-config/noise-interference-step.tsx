/**
 * 轮次步骤③：噪声与干扰（11_用例域.md §5.1）。
 * INT-996 接线：背景噪声/声纹注册/干扰人全部改真实数据源——
 * 噪声音频走真实音频库（AudioSelectDialog audioType='noise'，GET /audios 经 audioLibraryApi），
 * 播放目标只列逻辑音箱（GET /playback-devices/speaker-groups；实体设备由执行时按实验室换绑）；
 * 受控组件（value/onChange），保存侧由抽屉写入真实契约 config.rounds[].audios[].background_noise/interferers
 * + algorithm_params 独立列 voiceprint 字段。
 * 背景噪声节（噪声音频卡 + 添加/移除 + 声压级 + 循环 + 逻辑音箱 chips 多选）+
 * 声纹注册配置节（启用→注册音频选择卡 + 逻辑音箱 Select + 声压级 + 注册后等待秒数 0-60 + 提示）+
 * 干扰人配置节（干扰人列表卡「干扰音频* + 逻辑音箱 + 声压级 dB + 开始延迟秒 + 循环播放 Switch」+
 * 添加/删除；导入未匹配警示条）。
 */
import { AudioWaveform, Plus, Trash2, TriangleAlert, UserRound } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { usePlaybackSpeakerGroups } from '@/application/devices/use-devices'
import type {
  RoundInterfererDraft,
  RoundNoiseDraft,
} from '@/features/testcases/modals/round-config/round-nav'
import { AudioSelectDialog } from '@/features/testcases/modals/audio/audio-select-dialog'

const formatDuration = (s: number | null | undefined) => {
  if (s == null) return '—'
  const sec = Math.round(s)
  return sec < 60 ? `${sec}s` : sec % 60 === 0 ? `${sec / 60}m` : `${Math.floor(sec / 60)}m ${sec % 60}s`
}

/** 逻辑音箱选项文案（用例只关联逻辑音箱，不再直接选实体播放设备） */
const speakerGroupLabel = (group: { name: string }): string => `[逻辑音箱] ${group.name}`

let ifrSeq = 0
const nextIfrId = () => `ifr-${++ifrSeq}`

const defaultInterferer = (): RoundInterfererDraft => ({
  id: nextIfrId(),
  audioId: null,
  audioName: null,
  playbackDeviceId: null,
  speakerGroupId: null,
  spl: 70,
  startDelay: 0,
  loop: false,
})

export function NoiseInterferenceStep({
  value,
  onChange,
}: {
  /** 当前轮噪声与干扰草稿（受控；由抽屉按 config.rounds[].audios[].background_noise/interferers + algorithm_params 回填） */
  value: RoundNoiseDraft
  onChange: (next: RoundNoiseDraft) => void
}) {
  const groupsQuery = usePlaybackSpeakerGroups()
  const groups = useMemo(() => groupsQuery.data ?? [], [groupsQuery.data])
  /** 逻辑音箱下拉项（声纹/干扰人共用） */
  const groupItems = useMemo(
    () => groups.map((group) => ({ value: String(group.id), label: speakerGroupLabel(group) })),
    [groups]
  )

  const [bgPickerOpen, setBgPickerOpen] = useState(false)
  const [vpPickerOpen, setVpPickerOpen] = useState(false)
  const [ifrPickerIndex, setIfrPickerIndex] = useState<number | null>(null)

  const update = (patch: Partial<RoundNoiseDraft>) => onChange({ ...value, ...patch })

  const bg = value.backgroundNoise
  const vp = value.voiceprint

  /** 回填/导入产生的「文件名当音频 id」干扰项（audio_id 缺失时 codec 以文件名落 audioId） */
  const nameResolvedInterferers = value.interferers.filter(
    (ifr) =>
      typeof ifr.audioId === 'string' &&
      ifr.audioId !== '' &&
      Number.isNaN(Number(ifr.audioId))
  )

  const setBgAudio = (audio: { id: number | string; name: string; duration?: number | null; tags?: string[] }) => {
    const current = bg ?? { audioId: null, audioName: null, audio: null, spl: 94, deviceIds: [], speakerGroupIds: [], loop: true }
    update({
      backgroundNoise: {
        ...current,
        audioId: audio.id,
        audioName: audio.name,
        audio: { id: audio.id, name: audio.name, duration: audio.duration ?? null, tags: audio.tags ?? [] },
      },
    })
  }

  const toggleBgGroup = (id: string) => {
    if (!bg) return
    const next = new Set((bg.speakerGroupIds ?? []).map(String))
    if (next.has(id)) next.delete(id)
    else next.add(id)
    update({
      backgroundNoise: {
        ...bg,
        speakerGroupIds: [...next]
          .map((v) => Number(v))
          .filter((n) => !Number.isNaN(n)),
      },
    })
  }

  const updateVoiceprint = (patch: Partial<RoundNoiseDraft['voiceprint']>) =>
    update({ voiceprint: { ...vp, ...patch } })

  const updateInterferer = (id: string, patch: Partial<RoundInterfererDraft>) =>
    update({ interferers: value.interferers.map((x) => (x.id === id ? { ...x, ...patch } : x)) })

  const groupStatus = (loading: boolean, error: boolean) => {
    if (loading) {
      return (
        <div className='flex h-8 items-center gap-2 rounded-md border px-3 text-sm text-muted-foreground'>
          <Spinner className='size-3.5' />
          加载逻辑音箱...
        </div>
      )
    }
    if (error) {
      return (
        <div className='rounded-md border px-3 py-1.5 text-sm'>
          <p className='text-destructive text-xs'>加载逻辑音箱失败</p>
          <Button type='button' variant='outline' size='sm' className='mt-1 h-6 text-xs' onClick={() => void groupsQuery.refetch()}>
            重试
          </Button>
        </div>
      )
    }
    return null
  }

  return (
    <div className='space-y-4'>
      {/* 背景噪声节 */}
      <section className='space-y-2'>
        <div className='flex items-center justify-between gap-2'>
          <h4 className='text-sm font-medium'>背景噪声</h4>
          {bg ? (
            <Button type='button' variant='ghost' size='sm' className='h-7 gap-1 text-destructive hover:text-destructive' onClick={() => update({ backgroundNoise: null })}>
              <Trash2 aria-hidden='true' className='size-3.5' />
              移除
            </Button>
          ) : (
            <Button type='button' variant='outline' size='sm' className='h-7 gap-1' onClick={() => setBgPickerOpen(true)}>
              <Plus aria-hidden='true' className='size-3.5' />
              添加噪声
            </Button>
          )}
        </div>

        {!bg ? (
          <div className='border-border/60 rounded-lg border border-dashed px-3 py-4 text-center'>
            <p className='text-muted-foreground text-sm'>未配置背景噪声，点击「添加噪声」开始配置</p>
          </div>
        ) : (
          <div className='space-y-3'>
            {/* 噪声音频卡（文件名 + 时长 + 标签 + 更换/试听） */}
            <div className='bg-background ring-foreground/10 flex flex-wrap items-center gap-3 rounded-lg p-3 ring-1'>
              <AudioWaveform aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
              <span className='min-w-0 flex-1 truncate text-sm'>{bg.audioName ?? bg.audio?.name ?? '—'}</span>
              {bg.audio?.duration != null && (
                <Badge variant='outline' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
                  {formatDuration(bg.audio.duration)}
                </Badge>
              )}
              {(bg.audio?.tags ?? []).slice(0, 3).map((t) => (
                <Badge key={t} variant='secondary' className='rounded-md px-1.5 text-[10px]'>
                  {t}
                </Badge>
              ))}
              <Button type='button' variant='ghost' size='sm' className='h-7' onClick={() => setBgPickerOpen(true)}>
                更换
              </Button>
            </div>

            <div className='grid gap-x-6 gap-y-3 sm:grid-cols-2'>
              <div className='space-y-1.5'>
                <Label className='text-sm'>噪声声压级 dB</Label>
                <Input type='number' min={0} max={140} value={bg.spl} className='h-8' onChange={(e) => update({ backgroundNoise: { ...bg, spl: Number(e.target.value) } })} />
                <p className='text-muted-foreground/70 text-xs'>建议值：94 dB（1kHz 校准点）</p>
              </div>
              <div className='flex items-center gap-2'>
                <Switch checked={bg.loop} onCheckedChange={(v) => update({ backgroundNoise: { ...bg, loop: v } })} aria-label='循环播放' id='round-bg-loop' />
                <Label htmlFor='round-bg-loop' className='text-sm font-normal'>循环播放</Label>
              </div>
            </div>

            {/* 逻辑音箱（可多选）chips */}
            <div className='space-y-1.5'>
              <Label className='text-sm'>逻辑音箱（可多选）</Label>
              {groupStatus(groupsQuery.isLoading, groupsQuery.isError) ?? (
                <div className='flex flex-wrap gap-1.5'>
                  {groups.length === 0 ? (
                    <p className='text-muted-foreground/70 text-xs'>暂无可用的逻辑音箱</p>
                  ) : (
                    groups.map((group) => {
                      const id = String(group.id)
                      const checked = (bg.speakerGroupIds ?? []).map(String).includes(id)
                      return (
                        <button
                          key={group.id}
                          type='button'
                          aria-pressed={checked}
                          onClick={() => toggleBgGroup(id)}
                          className={cn(
                            'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                            checked
                              ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                              : 'hover:bg-accent border-border text-muted-foreground'
                          )}
                        >
                          {speakerGroupLabel(group)}
                        </button>
                      )
                    })
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* 声纹注册配置节 */}
      <section className='space-y-2 border-t pt-3'>
        <div className='flex items-center justify-between'>
          <h4 className='text-sm font-medium'>声纹注册配置</h4>
          <Switch checked={vp.enabled} onCheckedChange={(v) => updateVoiceprint({ enabled: v })} aria-label='启用声纹注册' />
        </div>
        {vp.enabled && (
          <div className='bg-background ring-foreground/10 space-y-3 rounded-lg p-3 ring-1'>
            {/* 注册音频 */}
            <div className='space-y-1.5'>
              <Label className='text-sm'>注册音频</Label>
              {vp.audioId != null ? (
                <div className='bg-background ring-foreground/10 flex flex-wrap items-center gap-2 rounded-md px-3 py-2 ring-1'>
                  <AudioWaveform aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
                  <span className='min-w-0 flex-1 truncate text-sm'>{vp.audioName ?? `音频 #${vp.audioId}`}</span>
                  <Button type='button' variant='ghost' size='sm' className='h-7' onClick={() => setVpPickerOpen(true)}>
                    更换
                  </Button>
                  <Button type='button' variant='ghost' size='sm' className='h-7 text-destructive hover:text-destructive' onClick={() => updateVoiceprint({ audioId: null, audioName: null })}>
                    清除
                  </Button>
                </div>
              ) : (
                <button
                  type='button'
                  onClick={() => setVpPickerOpen(true)}
                  className='border-border/60 hover:bg-accent flex w-full items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-4 text-sm transition-colors sm:w-72'
                >
                  <Plus aria-hidden='true' className='text-muted-foreground size-3.5' />
                  选择注册音频
                </button>
              )}
            </div>
            <div className='grid gap-x-6 gap-y-3 sm:grid-cols-3'>
              <div className='space-y-1.5'>
                <Label className='text-sm'>逻辑音箱</Label>
                {groupStatus(groupsQuery.isLoading, groupsQuery.isError) ?? (
                  <Select
                    value={vp.speakerGroupId != null ? String(vp.speakerGroupId) : ''}
                    onValueChange={(v) =>
                      updateVoiceprint({ speakerGroupId: v ? Number(v) : null })
                    }
                    items={groupItems}
                  >
                    <SelectTrigger size='sm' className='h-8'>
                      <SelectValue placeholder='请选择逻辑音箱' />
                    </SelectTrigger>
                    <SelectContent>
                      {groupItems.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <div className='space-y-1.5'>
                <Label className='text-sm'>播放声压级 dB</Label>
                <Input type='number' min={0} max={100} value={vp.spl} className='h-8' onChange={(e) => updateVoiceprint({ spl: Number(e.target.value) })} />
              </div>
              <div className='space-y-1.5'>
                <Label className='text-sm'>注册后等待秒数</Label>
                <Input type='number' min={0} max={60} value={vp.waitSec} className='h-8' onChange={(e) => updateVoiceprint({ waitSec: Number(e.target.value) })} />
              </div>
            </div>
            <p className='text-muted-foreground/70 text-xs'>声纹注册完成后等待设备处理的时间（0-60s）</p>
          </div>
        )}
      </section>

      {/* 干扰人配置节 */}
      <section className='space-y-2 border-t pt-3'>
        <div className='flex items-center justify-between'>
          <h4 className='text-sm font-medium'>干扰人配置</h4>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1'
            onClick={() => update({ interferers: [...value.interferers, defaultInterferer()] })}
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加干扰人
          </Button>
        </div>
        {value.interferers.length === 0 ? (
          <p className='text-muted-foreground py-2 text-center text-sm'>暂无干扰人配置</p>
        ) : (
          value.interferers.map((ifr, index) => (
            <div key={ifr.id} className='bg-background ring-foreground/10 rounded-lg p-3 ring-1'>
              <div className='flex items-center gap-2'>
                <UserRound aria-hidden='true' className='text-muted-foreground size-4' />
                <span className='text-sm font-medium'>干扰人 {index + 1}</span>
                <Button
                  type='button'
                  variant='ghost'
                  size='icon-sm'
                  aria-label={`删除干扰人 ${index + 1}`}
                  className='hover:text-destructive ms-auto size-7'
                  onClick={() => update({ interferers: value.interferers.filter((x) => x.id !== ifr.id) })}
                >
                  <Trash2 aria-hidden='true' className='size-3.5' />
                </Button>
              </div>
              <div className='mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-3'>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>干扰音频 *</Label>
                  <div className='flex items-center gap-1'>
                    <div className='border-border/60 bg-background ring-foreground/10 flex h-8 min-w-0 flex-1 items-center gap-1 rounded-md px-2 ring-1'>
                      <AudioWaveform aria-hidden='true' className='text-muted-foreground size-3 shrink-0' />
                      <span className='min-w-0 flex-1 truncate text-xs'>
                        {ifr.audioName ?? (ifr.audioId != null ? `音频 #${ifr.audioId}` : '未选择音频')}
                      </span>
                    </div>
                    <Button type='button' variant='outline' size='sm' className='h-8 shrink-0' onClick={() => setIfrPickerIndex(index)}>
                      选择
                    </Button>
                  </div>
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>逻辑音箱</Label>
                  {groupStatus(groupsQuery.isLoading, groupsQuery.isError) ?? (
                    <Select
                      value={ifr.speakerGroupId != null ? String(ifr.speakerGroupId) : ''}
                      onValueChange={(v) =>
                        updateInterferer(ifr.id, { speakerGroupId: v ? Number(v) : null })
                      }
                      items={groupItems}
                    >
                      <SelectTrigger size='sm' className='h-8'>
                        <SelectValue placeholder='请选择逻辑音箱' />
                      </SelectTrigger>
                      <SelectContent>
                        {groupItems.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
                <div className='grid grid-cols-2 gap-3'>
                  <div className='space-y-1.5'>
                    <Label className='text-sm'>声压级 dB</Label>
                    <Input type='number' min={0} max={100} value={ifr.spl} className='h-8' onChange={(e) => updateInterferer(ifr.id, { spl: Number(e.target.value) })} />
                  </div>
                  <div className='space-y-1.5'>
                    <Label className='text-sm'>开始延迟秒</Label>
                    <Input type='number' min={0} value={ifr.startDelay} className='h-8' onChange={(e) => updateInterferer(ifr.id, { startDelay: Number(e.target.value) })} />
                  </div>
                </div>
              </div>
              <div className='mt-2 flex items-center gap-2'>
                <Switch checked={ifr.loop} onCheckedChange={(v) => updateInterferer(ifr.id, { loop: v })} aria-label={`干扰人 ${index + 1} 循环播放`} />
                <span className='text-sm'>循环播放</span>
              </div>
            </div>
          ))
        )}
        {/* 导入未匹配警示条（数据驱动：仅当存在「按文件名解析」的干扰音频时显示——
            回填时 audio_id 缺失会以文件名落 audioId，数字 id 才是真实音频库记录） */}
        {nameResolvedInterferers.length > 0 && (
          <div className='flex items-start gap-2 rounded-lg border border-dashed p-2 text-xs'>
            <TriangleAlert aria-hidden='true' className='text-warning mt-0.5 size-3.5 shrink-0' />
            <p className='text-muted-foreground'>
              导入时未匹配到音频 ID 的干扰音频：
              {nameResolvedInterferers
                .slice(0, 3)
                .map((ifr) => ifr.audioName ?? String(ifr.audioId))
                .join('、')}
              {nameResolvedInterferers.length > 3
                ? ` 等 ${nameResolvedInterferers.length} 个`
                : ''}
              ，保存后后端会按文件名解析。
            </p>
          </div>
        )}
      </section>

      {/* 音频选择子弹窗（噪声单选） */}
      <AudioSelectDialog
        open={bgPickerOpen}
        onOpenChange={setBgPickerOpen}
        mode='single'
        audioType='noise'
        title='选择噪声音频'
        initialSelected={bg?.audioId != null ? [{ id: bg.audioId }] : []}
        onConfirm={(selected) => {
          const audio = selected[0]
          if (audio) setBgAudio(audio)
        }}
      />
      <AudioSelectDialog
        open={vpPickerOpen}
        onOpenChange={setVpPickerOpen}
        mode='single'
        audioType='noise'
        title='选择声纹注册音频'
        initialSelected={vp.audioId != null ? [{ id: vp.audioId }] : []}
        onConfirm={(selected) => {
          const audio = selected[0]
          if (audio) updateVoiceprint({ audioId: audio.id, audioName: audio.name })
        }}
      />
      {ifrPickerIndex != null && value.interferers[ifrPickerIndex] && (
        <AudioSelectDialog
          open
          onOpenChange={(open) => !open && setIfrPickerIndex(null)}
          mode='single'
          audioType='noise'
          title='选择干扰人音频'
          initialSelected={value.interferers[ifrPickerIndex].audioId != null ? [{ id: value.interferers[ifrPickerIndex].audioId! }] : []}
          onConfirm={(selected) => {
            const audio = selected[0]
            if (audio) {
              const target = value.interferers[ifrPickerIndex]
              if (target) updateInterferer(target.id, { audioId: audio.id, audioName: audio.name })
            }
          }}
        />
      )}
    </div>
  )
}
