/**
 * 音频试听弹窗（§6.14；音频行「预览」入口）。
 * 播放模式 Select「浏览器播放/实验室播放」（playbackMode 默认 frontend）+ 播放器。
 * INT-645 接线双模式：
 * - 浏览器播放 = GET /audios/{id}/stream 返 JSON 预签名 URL → <audio> 以该 URL 播放；
 * - 实验室播放 = POST /audios/{id}/preview（BatchPlaybackRequest：
 *   playback_device_id | playback_device_ids | device_unique_ids + spl + offset）→ 后端扬声器播放；
 *   停止 = POST /audios/{id}/stop-preview。
 */
import { Play, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

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
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AudioAsset } from '@/domain/models/audio'
import {
  preview,
  stopPreview,
  stream,
} from '@/infrastructure/api/audios-api'
import {
  MOCK_DEFAULT_SPL,
  MOCK_PLAYBACK_DEVICES,
} from '@/infrastructure/mock/audio-mock'
import { formatDuration } from '@/features/audio-import/lib/format'

export type AudioPreviewDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

export function AudioPreviewDialog(props: AudioPreviewDialogProps) {
  const [playbackMode, setPlaybackMode] = useState<'frontend' | 'laboratory'>(
    'frontend'
  )
  const [playing, setPlaying] = useState(false)
  const [pending, setPending] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [playbackDeviceId, setPlaybackDeviceId] = useState('1')
  const [spl, setSpl] = useState(String(MOCK_DEFAULT_SPL))
  const [offset, setOffset] = useState('0')
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audio = props.audio

  // 打开弹窗复位（重复打开/切换音频不残留上一状态）
  useEffect(() => {
    if (props.open) {
      setPlaying(false)
      setPending(false)
      setAudioUrl(null)
      setPlaybackMode('frontend')
    }
  }, [props.open])

  // 浏览器播放：stream 预签名 URL 就绪后显式起播（autoPlay 兜底）
  useEffect(() => {
    if (playbackMode === 'frontend' && audioUrl && audioRef.current) {
      void audioRef.current.play().catch(() => {})
    }
  }, [audioUrl, playbackMode])

  const handleOpenChange = (open: boolean) => {
    props.onOpenChange(open)
    if (!open) {
      if (playing && playbackMode === 'laboratory' && audio) {
        // 弹窗关闭时停止实验室播放（fire-and-forget）
        void stopPreview(audio.id)
      }
      setPlaying(false)
      setPending(false)
      setAudioUrl(null)
    }
  }

  const handlePlay = async () => {
    if (!audio || pending) return
    setPending(true)
    try {
      if (playbackMode === 'frontend') {
        const url = await stream(audio.id)
        setAudioUrl(url)
        setPlaying(true)
      } else {
        const result = await preview(audio.id, {
          playbackDeviceId: playbackDeviceId ? Number(playbackDeviceId) : null,
          spl: spl ? Number(spl) : null,
          offset: offset ? Number(offset) : 0,
        })
        if (result.success) {
          setPlaying(true)
          toast.success('已在实验室设备上开始试听')
        } else {
          toast.error(result.message ?? '试听启动失败，请重试')
        }
      }
    } catch {
      toast.error('试听启动失败，请重试')
    } finally {
      setPending(false)
    }
  }

  const handleStop = async () => {
    if (!audio) return
    if (playbackMode === 'frontend') {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.currentTime = 0
      }
      setAudioUrl(null)
      setPlaying(false)
      return
    }
    setPending(true)
    try {
      const result = await stopPreview(audio.id)
      if (result.success) {
        setPlaying(false)
        toast.success('已停止实验室试听')
      } else {
        toast.error(result.message ?? '停止试听失败，请重试')
      }
    } catch {
      toast.error('停止试听失败，请重试')
    } finally {
      setPending(false)
    }
  }

  const handleModeChange = (value: string) => {
    const mode = value === 'laboratory' ? 'laboratory' : 'frontend'
    if (mode !== playbackMode) {
      // 切换播放模式先停止当前播放
      if (playing && playbackMode === 'laboratory' && audio) {
        void stopPreview(audio.id)
      }
      setPlaying(false)
      setPending(false)
      setAudioUrl(null)
    }
    setPlaybackMode(mode)
  }

  return (
    <Dialog open={props.open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>音频播放</DialogTitle>
          <DialogDescription>
            {audio ? `试听「${audio.name}」` : '试听音频'}
          </DialogDescription>
        </DialogHeader>

        {audio ? (
          <div className='space-y-4'>
            <div className='flex items-center gap-3'>
              <Button
                variant='outline'
                size='icon'
                aria-label={playing ? '停止播放' : '播放'}
                disabled={pending}
                onClick={playing ? handleStop : handlePlay}
              >
                {playing ? (
                  <Square aria-hidden='true' className='size-4' />
                ) : (
                  <Play aria-hidden='true' className='size-4' />
                )}
              </Button>
              <div className='min-w-0 flex-1'>
                <div className='truncate text-sm font-medium'>{audio.name}</div>
                <div className='text-muted-foreground flex items-center gap-2 text-xs'>
                  <span>{audio.format ?? '—'}</span>
                  <span className='font-mono tabular-nums'>
                    {formatDuration(audio.duration)}
                  </span>
                  <span>{audio.audioType === 'dry' ? '干声（信号音频）' : audio.audioType === 'noise' ? '噪声' : audio.audioType === 'prompt' ? '提示词音频' : '混合音频'}</span>
                </div>
              </div>
            </div>

            {playbackMode === 'frontend' ? (
              audioUrl ? (
                <audio
                  ref={audioRef}
                  src={audioUrl}
                  controls
                  autoPlay
                  className='w-full'
                  onEnded={() => setPlaying(false)}
                />
              ) : (
                <div className='bg-muted text-muted-foreground flex h-9 w-full items-center rounded-md px-2 text-xs'>
                  {pending ? '正在获取音频播放地址...' : '就绪，点击播放开始试听'}
                </div>
              )
            ) : (
              <div className='bg-muted flex h-9 w-full items-center rounded-md px-2 text-xs'>
                <span className={playing ? 'text-primary' : 'text-muted-foreground'}>
                  {pending
                    ? '正在启动实验室播放...'
                    : playing
                      ? '正在通过实验室设备播放'
                      : '就绪，点击播放通过实验室设备输出'}
                </span>
              </div>
            )}

            <div className='space-y-2'>
              <div className='text-muted-foreground text-sm font-medium'>
                试听配置
              </div>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='text-muted-foreground text-xs'>播放模式</span>
                <Select value={playbackMode} onValueChange={handleModeChange}>
                  <SelectTrigger size='sm' className='w-44' aria-label='播放模式'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='frontend'>浏览器播放</SelectItem>
                    <SelectItem value='laboratory'>实验室播放</SelectItem>
                  </SelectContent>
                </Select>
                {playbackMode === 'laboratory' && (
                  <span className='text-muted-foreground text-xs'>
                    通过实验室音频通道输出
                  </span>
                )}
              </div>

              {playbackMode === 'laboratory' && (
                <div className='flex flex-wrap items-end gap-x-4 gap-y-2'>
                  <div className='space-y-1'>
                    <Label
                      htmlFor='preview-playback-device'
                      className='text-muted-foreground text-xs'
                    >
                      播放设备
                    </Label>
                    <Select
                      value={playbackDeviceId}
                      onValueChange={(value) =>
                        setPlaybackDeviceId(value ?? '1')
                      }
                    >
                      <SelectTrigger
                        id='preview-playback-device'
                        size='sm'
                        className='w-44'
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {MOCK_PLAYBACK_DEVICES.map((device) => (
                          <SelectItem key={device.id} value={String(device.id)}>
                            {device.name}（{device.model}）
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className='space-y-1'>
                    <Label
                      htmlFor='preview-spl'
                      className='text-muted-foreground text-xs'
                    >
                      声压级（dB）
                    </Label>
                    <Input
                      id='preview-spl'
                      type='number'
                      min={30}
                      max={120}
                      value={spl}
                      onChange={(e) => setSpl(e.target.value)}
                      className='h-8 w-24'
                    />
                  </div>
                  <div className='space-y-1'>
                    <Label
                      htmlFor='preview-offset'
                      className='text-muted-foreground text-xs'
                    >
                      偏移量（秒）
                    </Label>
                    <Input
                      id='preview-offset'
                      type='number'
                      min={0}
                      value={offset}
                      onChange={(e) => setOffset(e.target.value)}
                      className='h-8 w-24'
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className='text-muted-foreground py-6 text-center text-sm'>
            未选择音频
          </p>
        )}

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => handleOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
