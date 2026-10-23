/**
 * 轮次步骤②：音频列表（11_用例域.md §5.1，音频卡列表 + 工具栏）。
 * 受控组件：value=RoundAudioDraft[]、onChange 回写轮次草稿——编辑真实用例由
 * config.rounds[].audios 回填（INT-877 P1-1：audio_id/audio_name/spl/playback_device_id
 * /playback_device_name 真实数据），变更并入保存侧 config.rounds[].audios。
 * 播放设备 Select 走真实 GET /playback-devices；音频文件选择/更换走音频库子弹窗
 * （AudioSelectDialog 真实 GET /audios）。卡头「音频 {n}｜文件名｜时长｜勾选」+ 操作
 * （复制/删除/试听）+ 标签 chips 行；卡体字段：音频文件*（真实文件名 + 更换钮）/
 * 播放设备（Select「{设备名} (通道 {n})」）/声压级 dB（number 40-100，默认 65）。
 * 工具栏：升序/降序/随机排序｜标签交错｜标签设备｜批量设备｜设备交叉｜批量声压｜清空——
 * 批量工具纯函数派生（application/domain），标签源=真实音频库 tags。
 */
import {
  ArrowDownAZ,
  ArrowUpAZ,
  Copy,
  GripVertical,
  Headphones,
  Library,
  Play,
  RefreshCcw,
  Shuffle,
  Tag,
  Tags,
  Trash2,
  Volume2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useAudioListBatch, type RoundAudioLike } from '@/application/testcases/use-audio-list-batch'
import { usePlaybackDevices } from '@/application/devices/use-devices'
import { fetchAudioLibrary } from '@/infrastructure/api/audioLibraryApi'
import type { RoundAudioDraft } from '@/features/testcases/modals/round-config/round-nav'
import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'
import { BatchDevicePanel } from '@/features/testcases/modals/round-config/batch-device-panel'
import { BatchSplPanel } from '@/features/testcases/modals/round-config/batch-spl-panel'
import { CrossDevicePanel } from '@/features/testcases/modals/round-config/cross-device-panel'
import { TagDevicePanel } from '@/features/testcases/modals/round-config/tag-device-panel'
import { TagInterleavePanel } from '@/features/testcases/modals/round-config/tag-interleave-panel'
import { AudioSelectDialog } from '@/features/testcases/modals/audio/audio-select-dialog'
import {
  AudioPreviewConfigDialog,
  type PreviewAudioItem,
} from '@/features/testcases/modals/audio-preview-config-dialog'

/** 真实播放设备（/playback-devices）→ 面板/Select 展示项「{设备名} (通道 {n}) [干声/噪声]」 */
function toDeviceOption(d: {
  id: number | string
  name: string
  channelIndex?: number | null
  deviceType?: string | null
}): PlaybackDeviceOption {
  return {
    id: String(d.id),
    name: d.name,
    channel: d.channelIndex ?? 1,
    type: d.deviceType === 'noise' ? '噪声' : '干声',
  }
}

type BatchPanel =
  | 'interleave'
  | 'tagDevice'
  | 'batchDevice'
  | 'crossDevice'
  | 'batchSpl'

let audioSeq = 0
const nextId = () => `audio-${++audioSeq}`

/** 音频库选择结果 → 轮次音频草稿（真实 audio_id/name/duration/tags；spl 默认 65、设备待选） */
function audioDraftFromAsset(file: {
  id: number | string
  name: string
  duration?: number | null
  tags?: string[]
}): RoundAudioDraft {
  return {
    id: nextId(),
    audioId: file.id,
    audioName: file.name,
    spl: 65,
    deviceId: '',
    deviceName: null,
    duration: file.duration ?? null,
    tags: file.tags ?? [],
  }
}

const formatSeconds = (s: number | null | undefined): string | null => {
  if (s == null) return null
  const sec = Math.round(s)
  return sec < 60 ? `${sec}s` : sec % 60 === 0 ? `${sec / 60}m` : `${Math.floor(sec / 60)}m ${sec % 60}s`
}

export function AudioListStep({
  value,
  onChange,
}: {
  value: RoundAudioDraft[]
  onChange: (audios: RoundAudioDraft[]) => void
}) {
  const devicesQuery = usePlaybackDevices()
  /** 真实播放设备（Select + 批量工具面板共用） */
  const deviceOptions = useMemo<PlaybackDeviceOption[]>(
    () => (devicesQuery.data ?? []).map(toDeviceOption),
    [devicesQuery.data]
  )

  /** 真实音频库（标签工具数据源 + 时长/标签展示；GET /audios 大页拉取） */
  const [audioLibrary, setAudioLibrary] = useState<
    ReadonlyMap<string, { tags: string[]; duration: number | null }>
  >(new Map())
  useEffect(() => {
    let cancelled = false
    void fetchAudioLibrary({ perPage: 200 })
      .then((r) => {
        if (cancelled) return
        setAudioLibrary(
          new Map(
            r.items.map((a) => [
              String(a.id),
              { tags: a.tags ?? [], duration: a.duration ?? null },
            ])
          )
        )
      })
      .catch(() => {
        // 音频库加载失败不阻断步骤；标签工具降级为行内 tags
      })
    return () => {
      cancelled = true
    }
  }, [])

  /** 单条音频标签解析（真实音频库 tags 优先，行内 tags fallback） */
  const tagsOfDraft = (audio: RoundAudioLike): readonly string[] => {
    if (audio.audioId != null) {
      const lib = audioLibrary.get(String(audio.audioId))
      if (lib && lib.tags.length > 0) return lib.tags
    }
    return audio.tags ?? []
  }

  /** 批量工具（标签源=真实音频库 tags；身份随 audioLibrary 变化） */
  const batch = useAudioListBatch(tagsOfDraft)

  /** 面板可选标签源（音频库 + 行内并集） */
  const allTags = useMemo(
    () => [
      ...new Set(
        [...audioLibrary.values()].flatMap((v) => v.tags).concat(value.flatMap((a) => a.tags ?? []))
      ),
    ],
    [audioLibrary, value]
  )

  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set())
  const [panel, setPanel] = useState<BatchPanel | null>(null)
  const [pickingFromLibrary, setPickingFromLibrary] = useState(false)
  /** 单卡更换音频（replacingIndex 非空 → 音频库子弹窗单选确认） */
  const [replacingIndex, setReplacingIndex] = useState<number | null>(null)
  /** 单卡试听对象（INT-1424：试听按钮 → 真实音频试听配置弹窗） */
  const [previewItem, setPreviewItem] = useState<PreviewAudioItem | null>(null)

  // 行身份变更（复制/标签交错克隆/批量工具）时清理失效勾选
  useEffect(() => {
    const alive = new Set(value.map((a) => a.id))
    setSelectedIds((prev) =>
      prev.size === 0 || [...prev].every((id) => alive.has(id))
        ? prev
        : new Set([...prev].filter((id) => alive.has(id)))
    )
  }, [value])

  const update = (id: string, patch: Partial<RoundAudioDraft>) =>
    onChange(value.map((a) => (a.id === id ? { ...a, ...patch } : a)))

  /** 批量替换（批量工具/清空：id 集合可能变化，失效勾选由上方 useEffect 清理） */
  const replaceAudios = (fn: (prev: RoundAudioDraft[]) => RoundAudioDraft[]) =>
    onChange(fn(value))

  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const tool = (label: string, icon: React.ReactNode, onClick: () => void) => (
    <Tooltip key={label}>
      <TooltipTrigger
        render={<Button type='button' variant='ghost' size='sm' className='h-7 gap-1' onClick={onClick} />}
      >
        {icon}
        {label}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )

  const closePanel = (open: boolean) => {
    if (!open) setPanel(null)
  }

  return (
    <div className='space-y-3'>
      {/* 工具栏 */}
      <div className='flex flex-wrap items-center gap-1'>
        {tool('升序', <ArrowUpAZ aria-hidden='true' className='size-3.5' />, () =>
          replaceAudios((prev) =>
            [...prev].sort((a, b) => (a.audioName ?? '').localeCompare(b.audioName ?? ''))
          )
        )}
        {tool('降序', <ArrowDownAZ aria-hidden='true' className='size-3.5' />, () =>
          replaceAudios((prev) =>
            [...prev].sort((a, b) => (b.audioName ?? '').localeCompare(a.audioName ?? ''))
          )
        )}
        {tool('随机排序', <Shuffle aria-hidden='true' className='size-3.5' />, () =>
          replaceAudios((prev) => [...prev].sort(() => Math.random() - 0.5))
        )}
        {tool('标签交错', <Tags aria-hidden='true' className='size-3.5' />, () => setPanel('interleave'))}
        {tool('标签设备', <Tag aria-hidden='true' className='size-3.5' />, () => setPanel('tagDevice'))}
        {tool('批量设备', <Headphones aria-hidden='true' className='size-3.5' />, () => setPanel('batchDevice'))}
        {tool('设备交叉', <RefreshCcw aria-hidden='true' className='size-3.5' />, () => setPanel('crossDevice'))}
        {tool('批量声压', <Volume2 aria-hidden='true' className='size-3.5' />, () => setPanel('batchSpl'))}
        {tool('清空', <Trash2 aria-hidden='true' className='size-3.5' />, () => replaceAudios(() => []))}
      </div>

      {value.length === 0 ? (
        <p className='text-muted-foreground py-6 text-center text-sm'>
          尚未添加音频，点击下方「从音频库选择」
        </p>
      ) : (
        value.map((audio, index) => {
          const device = deviceOptions.find((d) => d.id === audio.deviceId)
          const duration = formatSeconds(
            audio.audioId != null ? audioLibrary.get(String(audio.audioId))?.duration ?? audio.duration : audio.duration
          )
          const tags = tagsOfDraft(audio)
          return (
            <div key={audio.id} className='bg-background ring-foreground/10 rounded-lg p-3 ring-1'>
              <div className='flex items-center gap-2'>
                <Checkbox
                  checked={selectedIds.has(audio.id)}
                  onCheckedChange={() => toggleSelect(audio.id)}
                  aria-label={`勾选音频 ${index + 1}`}
                  className='shrink-0'
                />
                <GripVertical aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
                <span className='text-sm font-medium'>音频 {index + 1}</span>
                <span className='text-muted-foreground min-w-0 flex-1 truncate text-xs'>{audio.audioName ?? '—'}</span>
                <span className='text-muted-foreground/60 font-mono text-xs tabular-nums'>{duration ?? ''}</span>
                <div className='ms-auto flex shrink-0 items-center gap-0.5'>
                  {audio.audioId != null && (
                    <Button
                      type='button'
                      variant='ghost'
                      size='icon-sm'
                      aria-label='试听'
                      className='size-7'
                      onClick={() =>
                        setPreviewItem({
                          id: audio.audioId as number | string,
                          name: audio.audioName,
                          spl: audio.spl,
                          // 音频库时长兜底：实验室播放无浏览器流，播放器总时长靠它（INT-1424 UX 复核）
                          duration:
                            audioLibrary.get(String(audio.audioId))?.duration ?? audio.duration ?? null,
                          deviceLabels: device
                            ? [`${device.name} (通道 ${device.channel}) [${device.type}]`]
                            : [],
                          // 实验室播放按用例配置的播放设备发送（INT-1424 终审 P2-2）
                          deviceIds: audio.deviceId ? [audio.deviceId] : [],
                        })
                      }
                    >
                      <Play aria-hidden='true' className='size-3.5' />
                    </Button>
                  )}
                  <Button
                    type='button'
                    variant='ghost'
                    size='icon-sm'
                    aria-label='复制音频'
                    className='size-7'
                    onClick={() =>
                      replaceAudios((prev) => [...prev, { ...audio, id: nextId() }])
                    }
                  >
                    <Copy aria-hidden='true' className='size-3.5' />
                  </Button>
                  <Button
                    type='button'
                    variant='ghost'
                    size='icon-sm'
                    aria-label='删除音频'
                    className='hover:text-destructive size-7'
                    onClick={() => replaceAudios((prev) => prev.filter((a) => a.id !== audio.id))}
                  >
                    <Trash2 aria-hidden='true' className='size-3.5' />
                  </Button>
                </div>
              </div>
              {/* 标签 chips（§5.1 卡头；标签交错/标签设备走查依赖可见标签） */}
              {tags.length > 0 && (
                <div className='mt-2 flex flex-wrap gap-1'>
                  {tags.map((t) => (
                    <Badge key={t} variant='outline' className='rounded-md px-1.5 text-[10px]'>
                      {t}
                    </Badge>
                  ))}
                </div>
              )}
              <div className='mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-3'>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>音频文件 *</Label>
                  <div className='flex items-center gap-1.5'>
                    <div className='bg-background ring-foreground/10 flex h-8 min-w-0 flex-1 items-center gap-1 rounded-md px-2 ring-1'>
                      <Play aria-hidden='true' className='text-muted-foreground size-3 shrink-0' />
                      <span className='min-w-0 flex-1 truncate text-xs'>{audio.audioName ?? '—'}</span>
                    </div>
                    <Button
                      type='button'
                      variant='outline'
                      size='sm'
                      className='h-8 shrink-0'
                      onClick={() => setReplacingIndex(index)}
                    >
                      更换
                    </Button>
                  </div>
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>播放设备</Label>
                  <Select
                    value={audio.deviceId}
                    onValueChange={(v) =>
                      v != null &&
                      update(audio.id, {
                        deviceId: v,
                        deviceName: deviceOptions.find((d) => d.id === v)?.name ?? null,
                      })
                    }
                    // 闭合态按声明式 items 解析文案；缺省时 base-ui 回退原始 value（设备记录 id）
                    items={deviceOptions.map((d) => ({
                      value: d.id,
                      label: `${d.name} (通道 ${d.channel}) [${d.type}]`,
                    }))}
                  >
                    <SelectTrigger size='sm' className='h-8'>
                      <SelectValue placeholder='请选择设备' />
                    </SelectTrigger>
                    <SelectContent>
                      {deviceOptions.map((d) => (
                        <SelectItem key={d.id} value={d.id}>
                          {d.name} (通道 {d.channel}) [{d.type}]
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>声压级 dB</Label>
                  <Input
                    type='number'
                    min={40}
                    max={100}
                    value={audio.spl}
                    className='h-8'
                    onChange={(e) => update(audio.id, { spl: Number(e.target.value) })}
                  />
                </div>
              </div>
              <p className='text-muted-foreground/60 mt-2 text-xs'>
                设备：{device ? `${device.name} (通道 ${device.channel}) [${device.type}]` : '—'}
              </p>
            </div>
          )
        })
      )}

      <div className='flex flex-wrap items-center gap-2'>
        {/* INT-1424：音频库导入为唯一入口（删除重复的「+ 添加音频」按钮，交互语义保留） */}
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='h-8 gap-1'
          onClick={() => setPickingFromLibrary(true)}
        >
          <Library aria-hidden='true' className='size-3.5' />
          从音频库选择
        </Button>
      </div>

      {/* 批量工具面板（§4 工具栏九件中的五件弹窗，真实设备/真实标签源） */}
      <TagInterleavePanel
        open={panel === 'interleave'}
        onOpenChange={closePanel}
        tags={allTags}
        onConfirm={(tags) => {
          replaceAudios(() => batch.tagInterleave(value, tags, nextId))
          toast.success(`已按标签「${tags.join(' / ')}」交错排序`)
        }}
      />
      <TagDevicePanel
        open={panel === 'tagDevice'}
        onOpenChange={closePanel}
        tags={allTags}
        devices={deviceOptions}
        onConfirm={(tag, deviceId) => {
          const hit = value.some((a) => tagsOfDraft(a).includes(tag))
          if (!hit) {
            toast.warning(`未找到命中标签「${tag}」的音频`)
            return
          }
          replaceAudios((prev) => batch.tagDevice(prev, tag, deviceId))
          toast.success(`已将标签「${tag}」命中的音频批量设置播放设备`)
        }}
      />
      <BatchDevicePanel
        open={panel === 'batchDevice'}
        onOpenChange={closePanel}
        devices={deviceOptions}
        selectedCount={selectedIds.size}
        onConfirm={(deviceId, scope) => {
          replaceAudios((prev) => batch.batchDevice(prev, deviceId, scope, selectedIds))
          toast.success(
            scope === 'selected' ? '已为勾选音频批量设置播放设备' : '已为全部音频批量设置播放设备'
          )
        }}
      />
      <CrossDevicePanel
        open={panel === 'crossDevice'}
        onOpenChange={closePanel}
        devices={deviceOptions}
        onConfirm={(deviceIds) => {
          replaceAudios((prev) => batch.crossDevice(prev, deviceIds))
          toast.success(`已按列表顺序轮转分配 ${deviceIds.length} 个设备`)
        }}
      />
      <BatchSplPanel
        open={panel === 'batchSpl'}
        onOpenChange={closePanel}
        selectedCount={selectedIds.size}
        onConfirm={(spl, scope) => {
          replaceAudios((prev) => batch.batchSpl(prev, spl, scope, selectedIds))
          toast.success(
            scope === 'selected'
              ? `已为勾选音频批量设置声压 ${spl} dB`
              : `已为全部音频批量设置声压 ${spl} dB`
          )
        }}
      />

      {/* 音频选择子弹窗（真实 GET /audios；添加/从音频库选择=追加，单卡更换=替换） */}
      <AudioSelectDialog
        open={pickingFromLibrary || replacingIndex != null}
        onOpenChange={(open) => {
          if (!open) {
            setPickingFromLibrary(false)
            setReplacingIndex(null)
          }
        }}
        mode='multi'
        title={replacingIndex != null ? '更换音频文件' : '选择音频文件'}
        initialSelected={
          replacingIndex != null && value[replacingIndex]?.audioId != null
            ? [{ id: value[replacingIndex].audioId as number | string }]
            : []
        }
        onConfirm={(selected) => {
          if (selected.length === 0) return
          if (replacingIndex != null && value[replacingIndex]) {
            const current = value[replacingIndex]
            // 多选态：当前音频预勾选，用户新增勾选=目标更换音频（与当前 id 不同者优先）
            const file =
              selected.find((a) => String(a.id) !== String(current.audioId)) ?? selected[0]
            onChange(
              value.map((a, i) =>
                i === replacingIndex
                  ? {
                      ...a,
                      audioId: file.id,
                      audioName: file.name,
                      duration: file.duration ?? null,
                      tags: file.tags ?? [],
                    }
                  : a
              )
            )
            toast.success('已更换音频文件')
          } else {
            onChange([...value, ...selected.map(audioDraftFromAsset)])
            toast.success(`已添加 ${selected.length} 个音频到轮次`)
          }
        }}
      />

      {/* 试听配置弹窗（INT-1424：真实音频流播放，无「演示」toast） */}
      <AudioPreviewConfigDialog
        open={previewItem != null}
        onOpenChange={(open) => !open && setPreviewItem(null)}
        caseItem={null}
        audioItem={previewItem}
      />
    </div>
  )
}
