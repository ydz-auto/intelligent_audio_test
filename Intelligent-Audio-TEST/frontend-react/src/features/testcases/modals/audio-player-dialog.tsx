/**
 * 音频播放器（11_用例域.md §5.2，Dialog `sm:max-w-lg` 内容态面板）。
 * 进度条（Slider 可点击/拖拽定位）+ 时间 `{current}/{duration}` tabular-nums +
 * 控制钮（播放/暂停、停止）+ 播放设备信息区（勾选设备「✓ {设备名}」）+ 错误条（Alert destructive 可关闭）。
 * 由 AudioPreviewConfigDialog 内嵌渲染（「开始试听」后切换 stage 呈现），
 * 播放进度 1s 步进模拟；接线后接 audio 流真实时长与播放状态。
 */
import { Pause, Play, Square, TriangleAlert, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'

/** mock 音频时长（秒；接线后取真实音频流时长） */
const MOCK_DURATION = 42

/** mock 勾选设备（实验室播放=用例配置设备；浏览器播放=前端播放无设备限制演示） */
const MOCK_DEVICES = ['音频接口 A (通道 1) [干声]', '音频接口 B (通道 2) [噪声]']

const formatClock = (s: number): string => {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export function AudioPlayerPanel({
  mode,
  onBack,
}: {
  mode: 'frontend' | 'backend'
  /** 返回试听配置（§5.2 播放器→配置双向切换） */
  onBack: () => void
}) {
  const [current, setCurrent] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      setCurrent((c) => {
        if (c >= MOCK_DURATION) {
          setPlaying(false)
          return MOCK_DURATION
        }
        return c + 1
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [playing])

  return (
    <div className='space-y-4'>
      {error && (
        <Alert variant='destructive'>
          <TriangleAlert aria-hidden='true' className='size-4 shrink-0' />
          <span className='min-w-0 flex-1'>{error}</span>
          <button
            type='button'
            aria-label='关闭错误提示'
            className='text-current'
            onClick={() => setError(null)}
          >
            <X aria-hidden='true' className='size-4' />
          </button>
        </Alert>
      )}

      <Slider
        min={0}
        max={MOCK_DURATION}
        value={current}
        aria-label='播放进度'
        onValueChange={(v) => setCurrent(Array.isArray(v) ? v[0] : v)}
      />
      <p className='text-muted-foreground font-mono text-xs tabular-nums'>
        {formatClock(current)} / {formatClock(MOCK_DURATION)}
      </p>

      <div className='flex flex-wrap items-center gap-2'>
        <Button
          size='sm'
          className='h-8 gap-1.5'
          aria-label={playing ? '暂停' : '播放'}
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? (
            <Pause aria-hidden='true' className='size-4' />
          ) : (
            <Play aria-hidden='true' className='size-4' />
          )}
          {playing ? '暂停' : '播放'}
        </Button>
        <Button
          size='sm'
          variant='outline'
          className='h-8 gap-1.5'
          aria-label='停止'
          onClick={() => {
            setPlaying(false)
            setCurrent(0)
          }}
        >
          <Square aria-hidden='true' className='size-4' />
          停止
        </Button>
      </div>

      <div className='space-y-1.5 rounded-lg border p-3'>
        <p className='text-muted-foreground text-xs font-medium'>
          播放设备{mode === 'backend' ? '（实验室播放）' : '（浏览器播放）'}
        </p>
        {MOCK_DEVICES.map((d) => (
          <p key={d} className='flex items-center gap-1.5 text-sm'>
            <span className='text-primary'>✓</span>
            {d}
          </p>
        ))}
      </div>

      <div className='flex justify-end'>
        <Button variant='ghost' size='sm' onClick={onBack}>
          返回试听配置
        </Button>
      </div>
    </div>
  )
}
