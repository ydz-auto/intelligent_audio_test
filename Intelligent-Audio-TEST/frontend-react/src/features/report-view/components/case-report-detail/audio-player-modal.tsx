/**
 * 音频播放 Modal（15_报告域.md §4.11，AudioPlayerModal 平移——照 V9.7.10 AudioPlayerModal.vue 抄写）。
 * 结构：音频标题 + 类型徽标 + 播放设备列表 → 进度条（点击/拖拽 seek）+ 当前/总时长
 * + 播放·暂停 / 停止 / 关闭 控制组 + 元信息（SPL/噪声级/播放顺序/音频 ID）+ 错误提示（可关闭）。
 * 真实 `<audio>`：audio.url 存在时走真实音频流（timeupdate/ended/error 驱动进度）；红线④ mock
 * 下多数音频无 url，退化为按 audio_id 派生时长模拟推进（seek 即时生效）。
 */
import { Pause, Play, Square, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { stream } from '@/infrastructure/api/audios-api'

/** 绝对外链（http/https）可直接作 <audio src>；相对路径/缺失时走 GET /audios/{id}/stream */
function toDirectPlayableUrl(url?: string): string {
  return url && /^https?:\/\//i.test(url) ? url : ''
}

export interface PlaybackDeviceInfo {
  name?: string
  status?: string
}

export interface AudioItemMeta {
  audio_id: number | string
  audio_name?: string
  audio_type?: string
  spl?: number
  play_order?: number
  noise_spl?: number
  device_name?: string
  /** 真实音频流地址（红线④：mock 一般无 url → 模拟推进；接线后填） */
  url?: string
  /** 播放设备列表（照 V9.7.10 selectedDevices；缺省按 device_name 兜底单设备） */
  playback_devices?: PlaybackDeviceInfo[]
  /** mock 时长（秒；缺省按 audio_id 派生演示值） */
  duration?: number
}

interface AudioPlayerModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio?: AudioItemMeta
}

/** V9.7.10 audioTypeLabel 同源中文（dry/noise/prompt/api/e2e 兜底未知类型） */
function audioTypeLabel(audioType?: string): string {
  const map: Record<string, string> = {
    dry: '干声 (信号音频)',
    noise: '噪声',
    prompt: '提示词音频',
    api: 'API测试音频',
    wakeword: '唤醒词音频',
    dialogue: '对话音频',
    final: '最终结果音频',
  }
  return map[audioType ?? ''] ?? '未知类型'
}

/** 演示时长（秒）：audio_id 数字哈希派生 8~42s，保证同 id 恒定；显式 duration/真实流优先 */
function mockDuration(audio?: AudioItemMeta): number {
  if (audio?.duration && audio.duration > 0) return audio.duration
  const id = String(audio?.audio_id ?? '')
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0
  return 8 + (hash % 35)
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function AudioPlayerModal({ open, onOpenChange, audio }: AudioPlayerModalProps) {
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [playError, setPlayError] = useState('')
  /** GET /audios/{id}/stream 换取的预签名播放地址（audio.url 非绝对外链时用） */
  const [streamUrl, setStreamUrl] = useState('')
  const [resolving, setResolving] = useState(false)
  /** 真实流的媒体时长（loadedmetadata 回填；无真实流时按 audio_id 派生演示值） */
  const [mediaDuration, setMediaDuration] = useState(0)
  const barRef = useRef<HTMLDivElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)

  const directUrl = toDirectPlayableUrl(audio?.url)
  const audioId =
    typeof audio?.audio_id === 'number'
      ? audio.audio_id
      : /^\d+$/.test(String(audio?.audio_id ?? ''))
        ? Number(audio?.audio_id)
        : null
  const playUrl = directUrl || streamUrl
  const isRealStream = Boolean(playUrl)
  const duration = mediaDuration > 0 ? mediaDuration : mockDuration(audio)

  const stop = useCallback(() => {
    setPlaying(false)
    setCurrent(0)
    const el = audioRef.current
    if (el) {
      el.pause()
      el.currentTime = 0
    }
  }, [])

  // 打开时重置播放态 + 错误；关闭时停止
  useEffect(() => {
    if (!open) {
      setPlaying(false)
      setCurrent(0)
      setPlayError('')
      setMediaDuration(0)
    } else {
      setCurrent(0)
      setPlayError('')
      setMediaDuration(0)
    }
  }, [open])

  // INT-1547 P2-2：report_service 给的 audios[].url 是网关相对路径（/api/audios/play/{id}，
  // 该路由未挂载，FEAT INT-1556）；有 audio_id 时统一经 GET /audios/{id}/stream 换预签名地址，
  // 取不到才退化为模拟播放。
  useEffect(() => {
    if (!open || directUrl || audioId === null) {
      setStreamUrl('')
      setResolving(false)
      return
    }
    let cancelled = false
    setStreamUrl('')
    setResolving(true)
    void stream(audioId)
      .then((url) => {
        if (!cancelled) setStreamUrl(url)
      })
      .catch(() => {
        if (!cancelled) setPlayError('音频播放地址获取失败，暂以模拟播放演示')
      })
      .finally(() => {
        if (!cancelled) setResolving(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, directUrl, audioId])

  // 真实流事件接线（timeupdate/ended/error → 进度/时长/错误）
  useEffect(() => {
    const el = audioRef.current
    if (!el || !isRealStream) return
    const onTimeUpdate = () => {
      if (!dragging) setCurrent(el.currentTime)
    }
    const onLoadedMeta = () => {
      if (Number.isFinite(el.duration) && el.duration > 0) {
        setMediaDuration(el.duration)
        setCurrent(0)
      }
    }
    const onEnded = () => {
      setPlaying(false)
      setCurrent(0)
    }
    const onError = () => {
      setPlaying(false)
      setPlayError('音频播放失败，请检查音频文件是否有效')
    }
    el.addEventListener('timeupdate', onTimeUpdate)
    el.addEventListener('loadedmetadata', onLoadedMeta)
    el.addEventListener('ended', onEnded)
    el.addEventListener('error', onError)
    return () => {
      el.removeEventListener('timeupdate', onTimeUpdate)
      el.removeEventListener('loadedmetadata', onLoadedMeta)
      el.removeEventListener('ended', onEnded)
      el.removeEventListener('error', onError)
    }
  }, [isRealStream, dragging])

  // mock 播放推进：无真实流时 playing 200ms 步进，到末尾自动停止（红④ 模拟）
  useEffect(() => {
    if (!playing || isRealStream) return
    const timer = setInterval(() => {
      setCurrent((prev) => {
        if (prev + 0.2 >= duration) {
          setPlaying(false)
          return duration
        }
        return prev + 0.2
      })
    }, 200)
    return () => clearInterval(timer)
  }, [playing, duration, isRealStream])

  const togglePlay = () => {
    setPlayError('')
    if (playing) {
      setPlaying(false)
      audioRef.current?.pause()
      return
    }
    setPlaying(true)
    const el = audioRef.current
    if (isRealStream && el) {
      try {
        void el.play().catch(() => {
          setPlaying(false)
          setPlayError('音频播放失败，请检查音频文件是否有效')
        })
      } catch {
        setPlaying(false)
        setPlayError('音频播放失败，请重试')
      }
    }
  }

  const seekFromClientX = (clientX: number) => {
    const rect = barRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0) return
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    const next = ratio * duration
    setCurrent(next)
    const el = audioRef.current
    if (isRealStream && el) el.currentTime = next
  }

  const progress = duration > 0 ? Math.min(100, (current / duration) * 100) : 0

  // 播放设备列表（照 V9.7.10 selectedDevices；缺省按 device_name 兜底）
  const devices = useMemo(() => {
    if (audio?.playback_devices && audio.playback_devices.length > 0) return audio.playback_devices
    if (audio?.device_name) return [{ name: audio.device_name, status: 'online' }]
    return []
  }, [audio])

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) stop()
      }}
    >
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{audioTypeLabel(audio?.audio_type)}</DialogTitle>
        </DialogHeader>
        {audio ? (
          <div className='space-y-4'>
            {/* 真实 <audio>：playUrl（外链或预签名地址）就绪即挂载，preload 取媒体时长/元数据 */}
            <audio ref={audioRef} src={playUrl || undefined} preload='metadata' className='hidden' />

            {/* 错误提示（照 V9.7.10 error-message，可关闭） */}
            {playError && (
              <div className='flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-900 dark:bg-red-950/40 dark:text-red-400'>
                <span className='min-w-0 flex-1'>{playError}</span>
                <button
                  type='button'
                  aria-label='关闭错误提示'
                  className='text-red-500 hover:text-red-700'
                  onClick={() => setPlayError('')}
                >
                  <X aria-hidden='true' className='size-3.5' />
                </button>
              </div>
            )}

            {/* 音频标题 + 类型徽标 */}
            <div className='text-center'>
              <p className='truncate text-base font-semibold'>
                {audio.audio_name ?? `音频 ${audio.audio_id}`}
              </p>
              <div className='mt-1.5 flex flex-wrap justify-center gap-1.5'>
                {audio.audio_type && <Badge variant='outline'>{audio.audio_type}</Badge>}
                {audio.device_name && <Badge variant='secondary'>{audio.device_name}</Badge>}
              </div>
            </div>

            {/* 播放器：进度条 + 时间 + 控制组（照 V9.7.10 progress-bar/time-info/controls） */}
            <div className='bg-muted/40 space-y-2 rounded-lg border p-4'>
              <div
                ref={barRef}
                role='slider'
                aria-label='播放进度'
                aria-valuemin={0}
                aria-valuemax={duration}
                aria-valuenow={Math.round(current)}
                className='relative h-2 cursor-pointer overflow-hidden rounded-full bg-muted transition-all hover:h-2.5'
                onMouseDown={(e) => {
                  e.preventDefault()
                  setDragging(true)
                  seekFromClientX(e.clientX)
                }}
                onMouseMove={(e) => {
                  if (dragging) seekFromClientX(e.clientX)
                }}
                onMouseUp={() => setDragging(false)}
                onMouseLeave={() => setDragging(false)}
                onClick={(e) => seekFromClientX(e.clientX)}
              >
                <div
                  className='bg-primary absolute inset-y-0 left-0 rounded-full'
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className='flex items-center justify-between px-1 text-xs font-mono tabular-nums'>
                <span className='bg-card rounded px-1.5 py-0.5 shadow-sm'>{formatTime(current)}</span>
                <span className='text-muted-foreground bg-card rounded px-1.5 py-0.5 shadow-sm'>{formatTime(duration)}</span>
              </div>

              <div className='flex items-center justify-center gap-2 pt-1'>
                <Button
                  size='sm'
                  className='h-8 gap-1 px-4'
                  aria-label={playing ? '暂停' : '播放'}
                  onClick={togglePlay}
                >
                  {playing ? (
                    <Pause aria-hidden='true' className='size-3.5' />
                  ) : (
                    <Play aria-hidden='true' className='size-3.5' />
                  )}
                  {playing ? '暂停' : '播放'}
                </Button>
                <Button
                  variant='secondary'
                  size='sm'
                  className='h-8 gap-1 px-4'
                  aria-label='停止'
                  onClick={stop}
                >
                  <Square aria-hidden='true' className='size-3' />
                  停止
                </Button>
              </div>
            </div>

            {/* 播放设备列表（照 V9.7.10 device-info） */}
            {devices.length > 0 && (
              <div className='rounded-lg border p-3'>
                <p className='text-muted-foreground mb-1 text-xs font-medium'>播放设备</p>
                <ul className='space-y-0.5'>
                  {devices.map((device, index) => (
                    <li key={`${device.name ?? index}`} className='flex items-center gap-2 text-sm'>
                      <span
                        aria-hidden='true'
                        className={cn(
                          'size-1.5 rounded-full',
                          device.status === 'offline' ? 'bg-destructive' : 'bg-success'
                        )}
                      />
                      <span className='font-medium'>{device.name ?? '未知设备'}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 元信息 */}
            <div className='text-muted-foreground grid grid-cols-2 gap-x-4 gap-y-1 text-xs'>
              <span>声压级 (SPL)：<span className='font-mono'>{audio.spl ?? '—'} dB</span></span>
              <span>噪声级：<span className='font-mono'>{audio.noise_spl ?? '—'} dB</span></span>
              <span>播放顺序：<span className='font-mono'>{audio.play_order ?? '—'}</span></span>
              <span>音频 ID：<span className='font-mono'>{audio.audio_id}</span></span>
            </div>

            <p className='text-muted-foreground text-center text-xs'>
              {playing
                ? '播放中…'
                : resolving
                  ? '正在获取音频地址…'
                  : isRealStream
                    ? '点击播放按钮预览音频'
                    : '点击播放按钮预览音频（mock，进度为模拟播放）'}
            </p>
          </div>
        ) : (
          <p className='text-muted-foreground p-4 text-center text-sm'>无音频信息</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
