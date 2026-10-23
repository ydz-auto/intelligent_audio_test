/**
 * 音频播放器（11_用例域.md §5.2，Dialog `sm:max-w-lg` 内容态面板）。
 * 进度条（Slider 可点击/拖拽定位）+ 时间 `{current}/{duration}` tabular-nums +
 * 控制钮（播放/暂停、停止）+ 播放设备信息区（勾选设备「✓ {设备名}」）+ 错误条（Alert destructive 可关闭）。
 * 由 AudioPreviewConfigDialog 内嵌渲染（「开始试听」后切换 stage 呈现）。
 * 时长取用例真实总时长（TestCaseListItem.totalDuration，由 config.rounds[].audios 累计），
 * 设备取用例 config.rounds[].audios[].playback_device_name（实验室播放实际设备），
 * 均无本地假数据；进度 1s 步进为无音频流端点前的本地走时（待接线 audio 流）。
 */
import { Pause, Play, Square, TriangleAlert, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import type { TestCaseListItem } from '@/domain/models/testCase'

const formatClock = (s: number): string => {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

/** 用例真实总时长（秒；无值返回 0 = 未获取到时长） */
const resolveDuration = (caseItem: TestCaseListItem | null): number =>
  caseItem?.totalDuration != null && caseItem.totalDuration > 0
    ? Math.round(caseItem.totalDuration)
    : 0

/** 用例各轮音频配置的播放设备名（去重；实验室播放实际使用的设备） */
const resolveDeviceNames = (caseItem: TestCaseListItem | null): string[] => {
  const rounds = caseItem?.config?.rounds
  if (!Array.isArray(rounds)) return []
  const names = new Set<string>()
  for (const round of rounds) {
    if (round == null || typeof round !== 'object') continue
    const audios = (round as { audios?: unknown }).audios
    if (!Array.isArray(audios)) continue
    for (const audio of audios) {
      if (audio == null || typeof audio !== 'object') continue
      const name = (audio as { playback_device_name?: unknown }).playback_device_name
      if (typeof name === 'string' && name.trim() !== '') names.add(name)
    }
  }
  return [...names]
}

export function AudioPlayerPanel({
  mode,
  caseItem,
  onBack,
}: {
  mode: 'frontend' | 'backend'
  /** 试听目标用例（真实时长与设备来源） */
  caseItem: TestCaseListItem | null
  /** 返回试听配置（§5.2 播放器→配置双向切换） */
  onBack: () => void
}) {
  const duration = resolveDuration(caseItem)
  const deviceNames = resolveDeviceNames(caseItem)
  const [current, setCurrent] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!playing || duration <= 0) return
    const timer = window.setInterval(() => {
      setCurrent((c) => (c >= duration ? duration : c + 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [playing, duration])

  // 播完自动停止（副作用不放进 state updater——StrictMode 下 updater 双调用安全）
  useEffect(() => {
    if (playing && duration > 0 && current >= duration) setPlaying(false)
  }, [playing, current, duration])

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
        max={duration}
        value={current}
        disabled={duration <= 0}
        aria-label='播放进度'
        onValueChange={(v) => setCurrent(Array.isArray(v) ? v[0] : v)}
      />
      <p className='text-muted-foreground font-mono text-xs tabular-nums'>
        {formatClock(current)} / {duration > 0 ? formatClock(duration) : '--:--'}
      </p>
      {duration <= 0 && (
        <p className='text-muted-foreground/70 text-xs'>
          未获取到该用例的音频时长（用例未关联音频）
        </p>
      )}

      <div className='flex flex-wrap items-center gap-2'>
        <Button
          size='sm'
          className='h-8 gap-1.5'
          aria-label={playing ? '暂停' : '播放'}
          disabled={duration <= 0}
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
        {mode === 'frontend' ? (
          <p className='text-muted-foreground text-sm'>浏览器播放不分设备</p>
        ) : deviceNames.length === 0 ? (
          <p className='text-muted-foreground text-sm'>该用例未配置播放设备</p>
        ) : (
          deviceNames.map((name) => (
            <p key={name} className='flex items-center gap-1.5 text-sm'>
              <span className='text-primary'>✓</span>
              {name}
            </p>
          ))
        )}
      </div>

      <div className='flex justify-end'>
        <Button variant='ghost' size='sm' onClick={onBack}>
          返回试听配置
        </Button>
      </div>
    </div>
  )
}
