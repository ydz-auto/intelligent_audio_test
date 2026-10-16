/**
 * 轮次步骤③：噪声与干扰（11_用例域.md §5.1）。
 * 背景噪声节（噪声音频卡 + 添加/移除）+ 声纹注册配置节（启用→注册音频选择卡 + 播放设备 +
 * 声压级 + 注册后等待秒数 0-60 + 提示）+ 干扰人配置节（干扰人列表卡「干扰音频* + 播放设备 +
 * 声压级 dB + 开始延迟秒 + 循环播放 Switch」+ 添加/删除；导入未匹配警示条）。
 */
import { AudioWaveform, Plus, Trash2, TriangleAlert, UserRound } from 'lucide-react'
import { useState } from 'react'

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

const MOCK_NOISE_FILES = ['粉红噪声_94dB.wav', '白噪声_85dB.wav', '街道环境音.wav']
const MOCK_DEVICES = [
  { id: 'dev-1', name: '音频接口 A', channel: 1, type: '干声' },
  { id: 'dev-2', name: '音频接口 B', channel: 2, type: '噪声' },
]

interface InterfererDraft {
  id: string
  fileId: string
  deviceId: string
  spl: number
  delaySec: number
  loop: boolean
}

let ifrSeq = 0
const nextIfrId = () => `ifr-${++ifrSeq}`

const defaultInterferer = (): InterfererDraft => ({
  id: nextIfrId(),
  fileId: MOCK_NOISE_FILES[0],
  deviceId: MOCK_DEVICES[1].id,
  spl: 70,
  delaySec: 0,
  loop: false,
})

export function NoiseInterferenceStep() {
  const [bgNoiseFile, setBgNoiseFile] = useState<string | null>(MOCK_NOISE_FILES[0])
  const [voiceprintEnabled, setVoiceprintEnabled] = useState(false)
  const [waitSec, setWaitSec] = useState(5)
  const [interferers, setInterferers] = useState<InterfererDraft[]>([])

  return (
    <div className='space-y-4'>
      {/* 背景噪声节 */}
      <section className='space-y-2'>
        <h4 className='text-sm font-medium'>背景噪声</h4>
        <div className='bg-background ring-foreground/10 flex items-center gap-3 rounded-lg p-3 ring-1'>
          <AudioWaveform aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
          {bgNoiseFile ? (
            <>
              <span className='min-w-0 flex-1 truncate text-sm'>{bgNoiseFile}</span>
              <Button type='button' variant='ghost' size='sm' className='h-7' onClick={() => setBgNoiseFile(null)}>
                移除
              </Button>
            </>
          ) : (
            <Select value='' onValueChange={(v) => setBgNoiseFile(v)}>
              <SelectTrigger size='sm' className='h-8 flex-1'>
                <SelectValue placeholder='选择噪声音频' />
              </SelectTrigger>
              <SelectContent>
                {MOCK_NOISE_FILES.map((n) => (
                  <SelectItem key={n} value={n}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        {bgNoiseFile && (
          <div className='grid gap-x-6 gap-y-3 pl-7 sm:grid-cols-2'>
            <div className='space-y-1.5'>
              <Label className='text-sm'>噪声声压级 dB</Label>
              <Input type='number' min={0} max={140} defaultValue={94} className='h-8' />
              <p className='text-muted-foreground/70 text-xs'>建议值：94 dB（1kHz 校准点）</p>
            </div>
            <div className='space-y-1.5'>
              <Label className='text-sm'>播放设备</Label>
              <Select defaultValue={MOCK_DEVICES[1].id}>
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
          </div>
        )}
      </section>

      {/* 声纹注册配置节 */}
      <section className='space-y-2 border-t pt-3'>
        <div className='flex items-center justify-between'>
          <h4 className='text-sm font-medium'>声纹注册配置</h4>
          <Switch checked={voiceprintEnabled} onCheckedChange={setVoiceprintEnabled} aria-label='启用声纹注册' />
        </div>
        {voiceprintEnabled && (
          <div className='bg-background ring-foreground/10 space-y-3 rounded-lg p-3 ring-1'>
            <div className='space-y-1.5'>
              <Label className='text-sm'>注册音频</Label>
              <Select defaultValue='au-01'>
                <SelectTrigger size='sm' className='h-8 w-full sm:w-72'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['au-01', 'au-02', 'au-03'].map((id) => (
                    <SelectItem key={id} value={id}>
                      注册音频 {id}（声纹样本）
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-x-6 gap-y-3 sm:grid-cols-3'>
              <div className='space-y-1.5'>
                <Label className='text-sm'>播放设备</Label>
                <Select defaultValue={MOCK_DEVICES[0].id}>
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
                <Label className='text-sm'>播放声压级 dB</Label>
                <Input type='number' min={0} max={100} defaultValue={75} className='h-8' />
              </div>
              <div className='space-y-1.5'>
                <Label className='text-sm'>注册后等待秒数</Label>
                <Input type='number' min={0} max={60} value={waitSec} className='h-8' onChange={(e) => setWaitSec(Number(e.target.value))} />
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
            onClick={() => setInterferers((prev) => [...prev, defaultInterferer()])}
          >
            <Plus aria-hidden='true' className='size-3.5' />
            添加干扰人
          </Button>
        </div>
        {interferers.length === 0 ? (
          <p className='text-muted-foreground py-2 text-center text-sm'>暂无干扰人配置</p>
        ) : (
          interferers.map((ifr, index) => (
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
                  onClick={() => setInterferers((prev) => prev.filter((x) => x.id !== ifr.id))}
                >
                  <Trash2 aria-hidden='true' className='size-3.5' />
                </Button>
              </div>
              <div className='mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-3'>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>干扰音频 *</Label>
                  <Select value={ifr.fileId} onValueChange={(v) => v != null && setInterferers((prev) => prev.map((x) => (x.id === ifr.id ? { ...x, fileId: v } : x)))}>
                    <SelectTrigger size='sm' className='h-8'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MOCK_NOISE_FILES.map((n) => (
                        <SelectItem key={n} value={n}>
                          {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>播放设备</Label>
                  <Select value={ifr.deviceId} onValueChange={(v) => v != null && setInterferers((prev) => prev.map((x) => (x.id === ifr.id ? { ...x, deviceId: v } : x)))}>
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
                <div className='grid grid-cols-2 gap-3'>
                  <div className='space-y-1.5'>
                    <Label className='text-sm'>声压级 dB</Label>
                    <Input type='number' min={0} max={100} value={ifr.spl} className='h-8' onChange={(e) => setInterferers((prev) => prev.map((x) => (x.id === ifr.id ? { ...x, spl: Number(e.target.value) } : x)))} />
                  </div>
                  <div className='space-y-1.5'>
                    <Label className='text-sm'>开始延迟秒</Label>
                    <Input type='number' min={0} value={ifr.delaySec} className='h-8' onChange={(e) => setInterferers((prev) => prev.map((x) => (x.id === ifr.id ? { ...x, delaySec: Number(e.target.value) } : x)))} />
                  </div>
                </div>
              </div>
              <div className='mt-2 flex items-center gap-2'>
                <Switch checked={ifr.loop} onCheckedChange={(v) => setInterferers((prev) => prev.map((x) => (x.id === ifr.id ? { ...x, loop: v } : x)))} aria-label={`干扰人 ${index + 1} 循环播放`} />
                <span className='text-sm'>循环播放</span>
              </div>
            </div>
          ))
        )}
        <div className='flex items-start gap-2 rounded-lg border border-dashed p-2 text-xs'>
          <TriangleAlert aria-hidden='true' className='text-warning mt-0.5 size-3.5 shrink-0' />
          <p className='text-muted-foreground'>
            导入时未匹配到音频 ID，保存后后端会按文件名解析（演示提示条）。
          </p>
        </div>
      </section>
    </div>
  )
}
