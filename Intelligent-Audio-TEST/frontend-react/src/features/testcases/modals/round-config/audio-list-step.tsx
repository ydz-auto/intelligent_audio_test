/**
 * 轮次步骤②：音频列表（11_用例域.md §5.1，音频卡列表 + 工具栏）。
 * 卡头「音频 {n}｜文件名｜时长｜标签 chips」+ 操作（复制/删除/试听）；
 * 卡体字段：音频文件*（Select 演示 Combobox）/播放设备（Select「{设备名} (通道 {n})」）/
 * 声压级 dB（number 40-100，默认 65）。
 * 工具栏：升序/降序/随机排序｜标签交错｜标签设备｜批量设备｜设备交叉｜批量声压｜清空（ghost sm + Tooltip）。
 */
import { ArrowDownAZ, ArrowUpAZ, Copy, GripVertical, Headphones, Play, Shuffle, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

const MOCK_AUDIO_FILES = [
  { id: 'au-01', name: '客厅_中文_命令集.wav', duration: '00:42' },
  { id: 'au-02', name: '车内_导航_1人.wav', duration: '01:05' },
  { id: 'au-03', name: '会议室_多人_中文.wav', duration: '02:30' },
  { id: 'au-04', name: '音乐背景_闹钟.wav', duration: '00:18' },
  { id: 'au-05', name: '英文_短信指令.flac', duration: '00:25' },
]

const MOCK_DEVICES = [
  { id: 'dev-1', name: '音频接口 A', channel: 1, type: '干声' },
  { id: 'dev-2', name: '音频接口 B', channel: 2, type: '噪声' },
  { id: 'dev-3', name: '蓝牙音箱', channel: 3, type: '干声' },
]

interface AudioDraft {
  id: string
  fileId: string
  deviceId: string
  spl: number
}

let audioSeq = 0
const nextId = () => `audio-${++audioSeq}`

const defaultAudio = (n: number): AudioDraft => ({
  id: nextId(),
  fileId: MOCK_AUDIO_FILES[n % MOCK_AUDIO_FILES.length].id,
  deviceId: MOCK_DEVICES[0].id,
  spl: 65,
})

export function AudioListStep({ presetCount = 2 }: { presetCount?: number }) {
  const [audios, setAudios] = useState<AudioDraft[]>(() =>
    Array.from({ length: presetCount }, (_, i) => defaultAudio(i))
  )

  const fileOf = (id: string) => MOCK_AUDIO_FILES.find((a) => a.id === id)
  const deviceOf = (id: string) => MOCK_DEVICES.find((d) => d.id === id)

  const update = (id: string, patch: Partial<AudioDraft>) =>
    setAudios((prev) => prev.map((a) => (a.id === id ? { ...a, ...patch } : a)))

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

  return (
    <div className='space-y-3'>
      {/* 工具栏 */}
      <div className='flex flex-wrap items-center gap-1'>
        {tool('升序', <ArrowUpAZ aria-hidden='true' className='size-3.5' />, () =>
          setAudios((prev) => [...prev].sort((a, b) => (fileOf(a.fileId)?.name ?? '').localeCompare(fileOf(b.fileId)?.name ?? '')))
        )}
        {tool('降序', <ArrowDownAZ aria-hidden='true' className='size-3.5' />, () =>
          setAudios((prev) => [...prev].sort((a, b) => (fileOf(b.fileId)?.name ?? '').localeCompare(fileOf(a.fileId)?.name ?? '')))
        )}
        {tool('随机排序', <Shuffle aria-hidden='true' className='size-3.5' />, () =>
          setAudios((prev) => [...prev].sort(() => Math.random() - 0.5))
        )}
        {tool('标签交错', <Badge variant='outline'>标签</Badge>, () => toast.success('按标签交错排序（演示）'))}
        {tool('批量设备', <Headphones aria-hidden='true' className='size-3.5' />, () => toast.success('批量设置播放设备（演示）'))}
        {tool('设备交叉', <X aria-hidden='true' className='size-3.5' />, () => toast.success('设备交叉轮转（演示）'))}
        {tool('批量声压', <Play aria-hidden='true' className='size-3.5' />, () => toast.success('批量设置声压级（演示）'))}
        {tool('清空', <Trash2 aria-hidden='true' className='size-3.5' />, () => setAudios([]))}
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
                <GripVertical aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
                <span className='text-sm font-medium'>音频 {index + 1}</span>
                <span className='text-muted-foreground text-xs truncate'>{file?.name}</span>
                <span className='text-muted-foreground/60 font-mono text-xs tabular-nums'>{file?.duration}</span>
                <div className='ms-auto flex items-center gap-0.5'>
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
                    onClick={() => setAudios((prev) => prev.filter((a) => a.id !== audio.id))}
                  >
                    <Trash2 aria-hidden='true' className='size-3.5' />
                  </Button>
                </div>
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
    </div>
  )
}
