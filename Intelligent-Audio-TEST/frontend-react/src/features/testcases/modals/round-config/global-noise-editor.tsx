/**
 * 全局背景噪声节（11_用例域.md §5.1.1 常驻节，case 级 config.background_noise）。
 * V9.7.10 CaseForm 全局噪声区块逐字平移换壳。
 * 未配置空态「未配置全局背景噪声，点击"添加全局噪声"开始配置」+「+ 添加全局噪声」ghost 钮
 * （已配置则钮位换「移除」destructive 软钮）；噪声音频卡（文件名+时长+标签 chips+更换/试听）；
 * 声压级 dB number 0-120 step 1 默认 60；循环播放 Switch 默认开；播放设备 chips 多选
 * （设备名存在但未匹配到 ID 时黄色警示 chip「未匹配到播放设备ID：{名}」，⚠️ 实施注意① 复用轮次级文案）。
 * 数据契约 config.background_noise = { audio_id, audio_name?, audio?, spl, device_ids[],
 *   playback_device_names[]?, playback_device_name?, device_names[]?, loop }（extra='allow' 兼容）。
 * 保存经 create/update 顶层 config；与轮次级噪声共存时 case 级优先播放。
 */
import { AudioWaveform, Plus, Trash2, TriangleAlert } from 'lucide-react'
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
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

/** mock 噪声音频列表 {id,name,tags,duration}（§5.1.1 音频选择子弹窗 audioType='noise' 单选） */
const MOCK_NOISE_AUDIOS = [
  { id: 'au-n1', name: '粉红噪声_94dB.wav', tags: ['粉红噪声'], duration: 180 },
  { id: 'au-n2', name: '白噪声_85dB.wav', tags: ['白噪声'], duration: 120 },
  { id: 'au-n3', name: '街道环境音.wav', tags: ['街道', '环境'], duration: 240 },
  { id: 'au-n4', name: '咖啡馆背景音.wav', tags: ['咖啡馆'], duration: 300 },
]

/** mock 播放设备 {id,name,channelIndex}（§5.1.1 设备 chips 多选） */
const MOCK_PLAYBACK_DEVICES = [
  { id: 'dev-1', name: '音频接口 A', channelIndex: 1 },
  { id: 'dev-2', name: '音频接口 B', channelIndex: 2 },
  { id: 'dev-3', name: '功放 左声道', channelIndex: 1 },
  { id: 'dev-4', name: '功放 右声道', channelIndex: 2 },
  { id: 'dev-5', name: '实验室喇叭组', channelIndex: 3 },
]

const formatDuration = (s: number) =>
  s < 60 ? `${s}s` : s % 60 === 0 ? `${s / 60}m` : `${Math.floor(s / 60)}m ${s % 60}s`

export function GlobalNoiseEditor() {
  const [configured, setConfigured] = useState(true)
  const [audio, setAudio] = useState<(typeof MOCK_NOISE_AUDIOS)[number] | null>(
    MOCK_NOISE_AUDIOS[0]
  )
  const [selectingAudio, setSelectingAudio] = useState(false)
  const [spl, setSpl] = useState(60)
  const [loop, setLoop] = useState(true)
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<Set<string>>(
    () => new Set(['dev-1', 'dev-3'])
  )
  /** 设备名存在但未匹配到 ID（旧配置残留名；黄色警示 chip） */
  const [unmatchedDeviceNames, setUnmatchedDeviceNames] = useState<string[]>([
    '旧喇叭组',
  ])

  const toggleDevice = (id: string) =>
    setSelectedDeviceIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-between gap-2'>
        <div>
          <h4 className='text-base font-medium'>全局背景噪声</h4>
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
            onClick={() => {
              setConfigured(false)
              setAudio(null)
              setSelectedDeviceIds(new Set())
              setUnmatchedDeviceNames([])
            }}
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
            onClick={() => {
              setConfigured(true)
              setAudio(MOCK_NOISE_AUDIOS[0])
              setSpl(60)
              setLoop(true)
              setSelectedDeviceIds(new Set(['dev-1']))
            }}
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加全局噪声
          </Button>
        )}
      </div>

      {!configured || !audio ? (
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
            {selectingAudio ? (
              <Select
                value={audio.id}
                onValueChange={(v) => {
                  const next = MOCK_NOISE_AUDIOS.find((a) => a.id === v)
                  if (next) setAudio(next)
                  setSelectingAudio(false)
                }}
              >
                <SelectTrigger size='sm' className='h-8 flex-1 sm:max-w-64'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MOCK_NOISE_AUDIOS.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <>
                <span className='min-w-0 flex-1 truncate text-sm'>{audio.name}</span>
                <Badge variant='outline' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
                  {formatDuration(audio.duration)}
                </Badge>
                {audio.tags.map((t) => (
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
                  onClick={() => toast.success(`正在试听：${audio.name}（演示）`)}
                >
                  试听
                </Button>
              </>
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
                value={spl}
                onChange={(e) => setSpl(Number(e.target.value))}
                className='h-8'
              />
            </div>
            <div className='flex items-center gap-2'>
              <Switch
                checked={loop}
                onCheckedChange={setLoop}
                aria-label='循环播放'
                id='global-noise-loop'
              />
              <Label htmlFor='global-noise-loop' className='text-sm font-normal'>
                循环播放
              </Label>
            </div>
          </div>

          {/* 播放设备（可多选）chips */}
          <div className='space-y-1.5'>
            <Label className='text-sm'>播放设备（可多选）</Label>
            <div className='flex flex-wrap gap-1.5'>
              {MOCK_PLAYBACK_DEVICES.map((d) => {
                const checked = selectedDeviceIds.has(d.id)
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
                    {d.name} (通道 {d.channelIndex})
                  </button>
                )
              })}
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
            <p className='text-muted-foreground/70 text-xs'>
              留空表示不指定播放设备；存在旧配置设备名但未匹配到 ID 时显示警示。
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
