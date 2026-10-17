/**
 * 音频播放 Modal（15_报告域.md §4.11，AudioPlayerModal 平移——照 V9.7.10 播放器交互抄写）。
 * 结构：音频标题 + 类型徽标 + 播放设备 → 进度条（点击/拖拽 seek）+ 当前/总时长
 * + 播放·暂停 / 停止 / 关闭 控制组 + 元信息（SPL/噪声级/播放顺序/音频 ID）。
 * 红线④ mock：无真实音频流，播放进度按音频时长模拟推进（audio_id 派生时长，seek 即时生效）。
 */
import { Pause, Play, Square } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export interface AudioItemMeta {
  audio_id: number | string
  audio_name?: string
  audio_type?: string
  spl?: number
  play_order?: number
  noise_spl?: number
  device_name?: string
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

/** 演示时长（秒）：audio_id 数字哈希派生 8~42s，保证同 id 恒定；显式 duration 优先 */
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
  const duration = useMemo(() => mockDuration(audio), [audio])
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [dragging, setDragging] = useState(false)
  const barRef = useRef<HTMLDivElement>(null)

  const stop = useCallback(() => {
    setPlaying(false)
    setCurrent(0)
  }, [])

  // 打开时重置播放态；关闭时停止
  useEffect(() => {
    if (!open) {
      setPlaying(false)
      setCurrent(0)
    }
  }, [open])

  // mock 播放推进：playing 时 200ms 步进，到末尾自动停止（无真实流，红④）
  useEffect(() => {
    if (!playing) return
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
  }, [playing, duration])

  const seekFromClientX = (clientX: number) => {
    const rect = barRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0) return
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    setCurrent(ratio * duration)
  }

  const progress = duration > 0 ? Math.min(100, (current / duration) * 100) : 0

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
            {/* 音频标题 + 类型/设备徽标 */}
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
                  onClick={() => setPlaying((v) => !v)}
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

            {/* 元信息 */}
            <div className='text-muted-foreground grid grid-cols-2 gap-x-4 gap-y-1 text-xs'>
              <span>声压级 (SPL)：<span className='font-mono'>{audio.spl ?? '—'} dB</span></span>
              <span>噪声级：<span className='font-mono'>{audio.noise_spl ?? '—'} dB</span></span>
              <span>播放顺序：<span className='font-mono'>{audio.play_order ?? '—'}</span></span>
              <span>音频 ID：<span className='font-mono'>{audio.audio_id}</span></span>
            </div>

            <p className='text-muted-foreground text-center text-xs'>
              {playing ? '播放中…' : '点击播放按钮预览音频（mock，进度为模拟播放）'}
            </p>
          </div>
        ) : (
          <p className='text-muted-foreground p-4 text-center text-sm'>无音频信息</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
