/**
 * 音频播放 Modal（15_报告域.md §4.11，AudioPlayerModal 平移——照 V9.7.10 AudioPlayerModal.vue 抄写）。
 * 结构：音频标题 + 类型徽标 + 播放设备列表 → 进度条（点击/拖拽 seek）+ 当前/总时长
 * + 播放·暂停 / 停止 / 关闭 控制组 + 元信息（SPL/噪声级/播放顺序/音频 ID）+ 错误提示（可关闭）。
 * 真实 `<audio>`：audio.url 存在时走真实音频流（timeupdate/ended/error 驱动进度）；
 * INT-1905 P3-3：无可用播放地址时不再按 audio_id 派生假时长模拟推进（FEAT INT-1556 收口前），
 * 改为「音频暂不可播放」失败态，不展示假进度与 mock 字样。
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
  /** 真实音频流地址（缺省时经 GET /audios/{id}/stream 换预签名地址；取不到即失败态） */
  url?: string
  /** 播放设备列表（照 V9.7.10 selectedDevices；缺省按 device_name 兜底单设备） */
  playback_devices?: PlaybackDeviceInfo[]
  /** 音频时长（秒；后端下发时用，真实流元数据加载后以媒体时长为准） */
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
    // INT-1688：用例执行详情弹窗的两类音频（结果音频 / 参考输入音频）
    result: '结果音频',
    reference: '参考音频',
  }
  return map[audioType ?? ''] ?? '未知类型'
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
  /** 真实流的媒体时长（loadedmetadata 回填；无真实流时为 0，不派生假时长） */
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
  // INT-1905 P3-3：无可用播放地址时整块换失败态、不做假进度；INT-1860：有真实流时总时长只认
  // 媒体元数据，元数据未到或流不可用（error / readyState=0）一律显示「—」，不派生假时长。
  const duration = mediaDuration > 0 ? mediaDuration : (isRealStream ? 0 : (audio?.duration ?? 0))
  const durationLabel = duration > 0 ? formatTime(duration) : '—'
  /** 待解析播放地址：有 audio_id 但尚无地址（挂载首帧 resolving 还没置位时也算，避免闪失败态） */
  const pendingStream = audioId !== null && !directUrl && !playError && !isRealStream
  /** 地址解析中（GET /audios/{id}/stream），既非可播也非失败 */
  const resolvingPlayUrl = !isRealStream && (resolving || pendingStream)
  /** 无可用播放地址的终态（FEAT INT-1556 未收口时的常见情形） */
  const unavailable = !isRealStream && !resolvingPlayUrl

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
  // 取不到即失败态（INT-1905 P3-3：不再退化为模拟播放）。
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
        if (!cancelled) setPlayError('音频播放地址获取失败，请稍后重试')
      })
      .finally(() => {
        if (!cancelled) setResolving(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, directUrl, audioId])

  // 真实流事件接线走 JSX props（见下方 <audio>，INT-1860）；无真实流不做模拟推进（INT-1905 P3-3）。

  const togglePlay = () => {
    setPlayError('')
    if (playing) {
      setPlaying(false)
      audioRef.current?.pause()
      return
    }
    // 无真实流时不可播放（失败态由下方 player panel 兜底，不做假进度）
    if (!isRealStream) return
    setPlaying(true)
    const el = audioRef.current
    if (el) {
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
    if (!isRealStream) return
    const rect = barRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0) return
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    const next = ratio * duration
    setCurrent(next)
    const el = audioRef.current
    if (el) el.currentTime = next
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
          /* INT-2090 P3：DialogContent 是 grid 容器，直接子级 grid item 的自动最小宽度=min-content，
             超长无断点 audio_name 会把内容区撑到完整宽度、truncate 失效并横向溢出；
             min-w-0 让 grid item 收缩回弹窗宽度，标题才能真正截断。 */
          <div className='min-w-0 space-y-4'>
            {/* 真实 <audio>：playUrl（外链或预签名地址）就绪即挂载，preload 取媒体时长/元数据。
                事件用 JSX props 而非 ref + useEffect 注册：弹窗内容经 Portal 异步挂载，
                用 effect 注册会在「打开时元素才出现」的 commit 里错过绑定（INT-1860）。 */}
            <audio
              ref={audioRef}
              src={playUrl || undefined}
              preload='metadata'
              className='hidden'
              onTimeUpdate={(e) => {
                if (!dragging) setCurrent(e.currentTarget.currentTime)
              }}
              onLoadedMetadata={(e) => {
                const el = e.currentTarget
                if (Number.isFinite(el.duration) && el.duration > 0) {
                  setMediaDuration(el.duration)
                  setCurrent(0)
                }
              }}
              onEnded={() => {
                setPlaying(false)
                setCurrent(0)
              }}
              onError={() => {
                setPlaying(false)
                setPlayError('音频播放失败，请检查音频文件是否有效')
              }}
            />

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

            {/* 音频标题 + 类型徽标（INT-2090：truncate 单行截断 + title 悬停显示完整名，
                超长音频名不换行撑爆弹窗、不把控制组挤出） */}
            <div className='text-center'>
              <p
                className='truncate text-base font-semibold'
                title={audio.audio_name ?? `音频 ${audio.audio_id}`}
              >
                {audio.audio_name ?? `音频 ${audio.audio_id}`}
              </p>
              <div className='mt-1.5 flex min-w-0 flex-wrap justify-center gap-1.5'>
                {audio.audio_type && <Badge variant='outline'>{audio.audio_type}</Badge>}
                {audio.device_name && (
                  <Badge variant='secondary' className='max-w-full'>
                    <span className='truncate' title={audio.device_name}>
                      {audio.device_name}
                    </span>
                  </Badge>
                )}
              </div>
            </div>

            {/* 播放器：进度条 + 时间 + 控制组（照 V9.7.10 progress-bar/time-info/controls） */}
            {unavailable ? (
              /* INT-1905 P3-3：无可用播放地址 → 失败态，不展示假进度与模拟播放 */
              <div className='bg-muted/40 rounded-lg border border-dashed p-6 text-center'>
                <p className='text-sm font-medium'>音频暂不可播放</p>
                <p className='text-muted-foreground mt-1 text-xs'>
                  该音频暂无可用播放地址，请稍后重试
                </p>
              </div>
            ) : resolvingPlayUrl ? (
              <div className='bg-muted/40 rounded-lg border p-6 text-center'>
                <p className='text-muted-foreground text-sm'>正在获取音频地址…</p>
              </div>
            ) : (
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
                <span
                  data-testid='audio-duration'
                  className='text-muted-foreground bg-card rounded px-1.5 py-0.5 shadow-sm'
                >
                  {durationLabel}
                </span>
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
            )}

            {/* 播放设备列表（照 V9.7.10 device-info） */}
            {devices.length > 0 && (
              <div className='rounded-lg border p-3'>
                <p className='text-muted-foreground mb-1 text-xs font-medium'>播放设备</p>
                <ul className='space-y-0.5'>
                  {devices.map((device, index) => (
                    <li
                      key={`${device.name ?? index}`}
                      className='flex min-w-0 items-center gap-2 text-sm'
                    >
                      <span
                        aria-hidden='true'
                        className={cn(
                          'size-1.5 shrink-0 rounded-full',
                          device.status === 'offline' ? 'bg-destructive' : 'bg-success'
                        )}
                      />
                      <span className='min-w-0 truncate font-medium' title={device.name}>
                        {device.name ?? '未知设备'}
                      </span>
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

            {isRealStream && (
              <p className='text-muted-foreground text-center text-xs'>
                {playing ? '播放中…' : '点击播放按钮预览音频'}
              </p>
            )}
          </div>
        ) : (
          <p className='text-muted-foreground p-4 text-center text-sm'>无音频信息</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
