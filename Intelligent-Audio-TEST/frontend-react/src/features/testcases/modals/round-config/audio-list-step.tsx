/**
 * 轮次步骤②：音频列表（11_用例域.md §5.1，音频卡列表 + 工具栏）。
 * 卡头「音频 {n}｜文件名｜时长｜勾选」+ 操作（复制/删除/试听）+ 标签 chips 行；
 * 卡体字段：音频文件*（Select 演示 Combobox）/播放设备（Select「{设备名} (通道 {n})」）/
 * 声压级 dB（number 40-100，默认 65）。
 * 工具栏：升序/降序/随机排序｜标签交错（≥2 标签 chip 选择面板）｜标签设备（标签→设备映射面板）｜
 * 批量设备｜设备交叉（多选设备按序轮转分配）｜批量声压｜清空（ghost sm + Tooltip）——
 * 五件批量工具真实交互（application/domain 纯函数派生，mock 态不接后端，INT-588 补全）。
 */
import {
  ArrowDownAZ,
  ArrowUpAZ,
  Copy,
  GripVertical,
  Headphones,
  Play,
  RefreshCcw,
  Shuffle,
  Tag,
  Tags,
  Trash2,
  Volume2,
} from 'lucide-react'
import { useState } from 'react'
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
import { useAudioListBatch } from '@/application/testcases/use-audio-list-batch'
import type {
  MockAudioFile,
  MockDevice,
} from '@/features/testcases/modals/round-config/audio-list-types'
import { BatchDevicePanel } from '@/features/testcases/modals/round-config/batch-device-panel'
import { BatchSplPanel } from '@/features/testcases/modals/round-config/batch-spl-panel'
import { CrossDevicePanel } from '@/features/testcases/modals/round-config/cross-device-panel'
import { TagDevicePanel } from '@/features/testcases/modals/round-config/tag-device-panel'
import { TagInterleavePanel } from '@/features/testcases/modals/round-config/tag-interleave-panel'

const MOCK_AUDIO_FILES: MockAudioFile[] = [
  { id: 'au-01', name: '客厅_中文_命令集.wav', duration: '00:42', tags: ['客厅', '中文', '命令集'] },
  { id: 'au-02', name: '车内_导航_1人.wav', duration: '01:05', tags: ['车内', '导航', '单人'] },
  { id: 'au-03', name: '会议室_多人_中文.wav', duration: '02:30', tags: ['会议室', '多人', '中文'] },
  { id: 'au-04', name: '音乐背景_闹钟.wav', duration: '00:18', tags: ['音乐背景', '闹钟'] },
  { id: 'au-05', name: '英文_短信指令.flac', duration: '00:25', tags: ['英文', '短信'] },
]

const MOCK_DEVICES: MockDevice[] = [
  { id: 'dev-1', name: '音频接口 A', channel: 1, type: '干声' },
  { id: 'dev-2', name: '音频接口 B', channel: 2, type: '噪声' },
  { id: 'dev-3', name: '蓝牙音箱', channel: 3, type: '干声' },
]

/** 标签源（页面级 mock；音频文件标签去重并集，INT-588 批量工具选择面板共用） */
const MOCK_TAGS = [...new Set(MOCK_AUDIO_FILES.flatMap((f) => f.tags))]

/** fileId → tags 映射（application 批量动作标签源；模块级常量保持身份稳定） */
const TAGS_BY_FILE = new Map(MOCK_AUDIO_FILES.map((f) => [f.id, f.tags]))

interface AudioDraft {
  id: string
  fileId: string
  deviceId: string
  spl: number
}

/** 列表 + 勾选态合并（批量工具替换列表后清理失效勾选，勾选态不残留） */
interface AudioListState {
  audios: AudioDraft[]
  selectedIds: ReadonlySet<string>
}

type BatchPanel =
  | 'interleave'
  | 'tagDevice'
  | 'batchDevice'
  | 'crossDevice'
  | 'batchSpl'

let audioSeq = 0
const nextId = () => `audio-${++audioSeq}`

const defaultAudio = (n: number): AudioDraft => ({
  id: nextId(),
  fileId: MOCK_AUDIO_FILES[n % MOCK_AUDIO_FILES.length].id,
  deviceId: MOCK_DEVICES[0].id,
  spl: 65,
})

export function AudioListStep({ presetCount = 2 }: { presetCount?: number }) {
  const batch = useAudioListBatch(TAGS_BY_FILE)
  const [state, setState] = useState<AudioListState>(() => ({
    audios: Array.from({ length: presetCount }, (_, i) => defaultAudio(i)),
    selectedIds: new Set(),
  }))
  const [panel, setPanel] = useState<BatchPanel | null>(null)

  const { audios, selectedIds } = state

  const fileOf = (id: string) => MOCK_AUDIO_FILES.find((a) => a.id === id)
  const deviceOf = (id: string) => MOCK_DEVICES.find((d) => d.id === id)

  /** 普通替换（复制/排序/单行更新：id 集合不变） */
  const setAudios = (fn: (prev: AudioDraft[]) => AudioDraft[]) =>
    setState((s) => ({ ...s, audios: fn(s.audios) }))

  /** 批量替换（批量工具/清空：id 集合可能变化，清理失效勾选） */
  const replaceAudios = (fn: (prev: AudioDraft[]) => AudioDraft[]) =>
    setState((s) => {
      const audios = fn(s.audios)
      const alive = new Set(audios.map((a) => a.id))
      const selectedIds =
        s.selectedIds.size === 0 || [...s.selectedIds].every((id) => alive.has(id))
          ? s.selectedIds
          : new Set([...s.selectedIds].filter((id) => alive.has(id)))
      return { audios, selectedIds }
    })

  const update = (id: string, patch: Partial<AudioDraft>) =>
    setAudios((prev) => prev.map((a) => (a.id === id ? { ...a, ...patch } : a)))

  const toggleSelect = (id: string) =>
    setState((s) => {
      const next = new Set(s.selectedIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { ...s, selectedIds: next }
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
          setAudios((prev) =>
            [...prev].sort((a, b) =>
              (fileOf(a.fileId)?.name ?? '').localeCompare(fileOf(b.fileId)?.name ?? '')
            )
          )
        )}
        {tool('降序', <ArrowDownAZ aria-hidden='true' className='size-3.5' />, () =>
          setAudios((prev) =>
            [...prev].sort((a, b) =>
              (fileOf(b.fileId)?.name ?? '').localeCompare(fileOf(a.fileId)?.name ?? '')
            )
          )
        )}
        {tool('随机排序', <Shuffle aria-hidden='true' className='size-3.5' />, () =>
          setAudios((prev) => [...prev].sort(() => Math.random() - 0.5))
        )}
        {tool('标签交错', <Tags aria-hidden='true' className='size-3.5' />, () => setPanel('interleave'))}
        {tool('标签设备', <Tag aria-hidden='true' className='size-3.5' />, () => setPanel('tagDevice'))}
        {tool('批量设备', <Headphones aria-hidden='true' className='size-3.5' />, () => setPanel('batchDevice'))}
        {tool('设备交叉', <RefreshCcw aria-hidden='true' className='size-3.5' />, () => setPanel('crossDevice'))}
        {tool('批量声压', <Volume2 aria-hidden='true' className='size-3.5' />, () => setPanel('batchSpl'))}
        {tool('清空', <Trash2 aria-hidden='true' className='size-3.5' />, () => replaceAudios(() => []))}
      </div>

      {audios.length === 0 ? (
        <p className='text-muted-foreground py-6 text-center text-sm'>尚未添加音频，点击下方「添加音频」</p>
      ) : (
        audios.map((audio, index) => {
          const file = fileOf(audio.fileId)
          const device = deviceOf(audio.deviceId)
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
                <span className='text-muted-foreground min-w-0 flex-1 truncate text-xs'>{file?.name}</span>
                <span className='text-muted-foreground/60 font-mono text-xs tabular-nums'>{file?.duration}</span>
                <div className='ms-auto flex shrink-0 items-center gap-0.5'>
                  <Button type='button' variant='ghost' size='icon-sm' aria-label='试听' className='size-7'>
                    <Play aria-hidden='true' className='size-3.5' />
                  </Button>
                  <Button
                    type='button'
                    variant='ghost'
                    size='icon-sm'
                    aria-label='复制音频'
                    className='size-7'
                    onClick={() => setAudios((prev) => [...prev, { ...audio, id: nextId() }])}
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
              <div className='mt-2 flex flex-wrap gap-1'>
                {file?.tags.map((t) => (
                  <Badge key={t} variant='outline' className='rounded-md px-1.5 text-[10px]'>
                    {t}
                  </Badge>
                ))}
              </div>
              <div className='mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-3'>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>音频文件 *</Label>
                  <Select value={audio.fileId} onValueChange={(v) => v != null && update(audio.id, { fileId: v })}>
                    <SelectTrigger size='sm' className='h-8'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MOCK_AUDIO_FILES.map((a) => (
                        <SelectItem key={a.id} value={a.id}>
                          {a.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>播放设备</Label>
                  <Select value={audio.deviceId} onValueChange={(v) => v != null && update(audio.id, { deviceId: v })}>
                    <SelectTrigger size='sm' className='h-8'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MOCK_DEVICES.map((d) => (
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

      <Button
        type='button'
        variant='outline'
        size='sm'
        className='h-8 gap-1'
        onClick={() => setAudios((prev) => [...prev, defaultAudio(prev.length)])}
      >
        + 添加音频
      </Button>

      {/* 批量工具面板（§4 工具栏九件中的五件弹窗，mock 态真实交互） */}
      <TagInterleavePanel
        open={panel === 'interleave'}
        onOpenChange={closePanel}
        tags={MOCK_TAGS}
        onConfirm={(tags) => {
          replaceAudios(() => batch.tagInterleave(audios, tags))
          toast.success(`已按标签「${tags.join(' / ')}」交错排序`)
        }}
      />
      <TagDevicePanel
        open={panel === 'tagDevice'}
        onOpenChange={closePanel}
        tags={MOCK_TAGS}
        devices={MOCK_DEVICES}
        onConfirm={(tag, deviceId) => {
          const hit = audios.some((a) => TAGS_BY_FILE.get(a.fileId)?.includes(tag))
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
        devices={MOCK_DEVICES}
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
        devices={MOCK_DEVICES}
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
    </div>
  )
}
