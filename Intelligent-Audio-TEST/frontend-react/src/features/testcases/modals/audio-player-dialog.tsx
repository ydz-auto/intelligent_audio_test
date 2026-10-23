/**
 * 音频播放器（11_用例域.md §5.2，Dialog `sm:max-w-lg` 内容态面板）。
 * 进度条（Slider 可点击/拖拽定位）+ 时间 `{current}/{duration}` tabular-nums +
 * 控制钮（播放/暂停、停止）+ 播放设备信息区（勾选设备「✓ {设备名}」）+ 错误条（Alert destructive 可关闭）。
 * 由 AudioPreviewConfigDialog 内嵌渲染（「开始试听」后切换 stage 呈现）。
 * 真实链路（对照 V9.7.10 AudioPlayerModal.vue，INT-1424 移除 mock）：
 * - 浏览器播放：GET /audios/{id}/stream → OSS 预签名 URL → HTMLAudioElement 播放，
 *   进度/时长取自音频流 metadata（无 mock 时长）；
 * - 实验室播放：POST /audios/{id}/preview 通知后端扬声器输出，进度按墙钟推进
 *   （设备端播放无浏览器流；offset 作为起点），停止/暂停走 POST /audios/{id}/stop-preview。
 */
import { Pause, Play, Square, TriangleAlert, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { usePlaybackDevices } from '@/application/devices/use-devices'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { fetchAudioDuration, preview, stopPreview, stream } from '@/infrastructure/api/audios-api'

const formatClock = (s: number): string => {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export function AudioPlayerPanel({
  mode,
  audioId,
  audioName,
  deviceLabels = [],
  deviceIds = [],
  spl,
  offset = 0,
  durationHint = null,
  onBack,
}: {
  mode: 'frontend' | 'backend'
  /** 音频 id（null 时不发起播放，仅展示空态） */
  audioId: number | string | null
  /** 音频文件名（标题区展示） */
  audioName?: string | null
  /** 播放设备标签（实验室播放=用例配置设备名列表；浏览器播放可为空） */
  deviceLabels?: string[]
  /** 播放设备记录 id（用例配置的 playback_device_id / 全局噪声 deviceIds）：
   *  实验室播放解析成 playback_device_ids + device_unique_ids 随请求发送（INT-1424 终审 P2-2） */
  deviceIds?: string[]
  /** 实验室播放声压级（dB） */
  spl?: number | null
  /** 实验室播放起点偏移（秒） */
  offset?: number
  /** 音频库已知总时长（秒）：浏览器播放先作占位、metadata 到达后覆盖；
   *  实验室播放无浏览器流，总时长全靠它兜底（V9.7.10 AudioPlayerModal 全模式取 metadata 同义） */
  durationHint?: number | null
  /** 返回试听配置（§5.2 播放器→配置双向切换） */
  onBack: () => void
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  /** 调用方未带时长时的兜底（按音频 id/文件名回查音频库，实验室播放取不到流 metadata） */
  const [resolvedDuration, setResolvedDuration] = useState<number | null>(null)
  /** 生效总时长：调用方传入优先，缺省用回查结果 */
  const hint = durationHint != null && durationHint > 0 ? durationHint : resolvedDuration
  const [current, setCurrent] = useState(0)
  const [duration, setDuration] = useState(hint != null && hint > 0 ? hint : 0)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** 播放设备（/playback-devices）：用例配置的设备 id → 记录 id + 设备唯一 id（V9.7.10
   *  playOnExternalDevices 的 playbackDeviceIds / deviceUniqueIds 口径） */
  const devicesQuery = usePlaybackDevices()
  const backendTargets = useMemo(() => {
    const all = devicesQuery.data ?? []
    return deviceIds.map((raw) => {
      const numeric = Number(raw)
      const hit = Number.isFinite(numeric)
        ? all.find((d) => Number(d.id) === numeric)
        : undefined
      return {
        id: hit ? Number(hit.id) : Number.isFinite(numeric) ? numeric : null,
        uniqueId: hit?.deviceUniqueId ?? null,
        name: hit?.name ?? null,
      }
    })
  }, [deviceIds, devicesQuery.data])
  const playbackDeviceIds = backendTargets
    .map((d) => d.id)
    .filter((id): id is number => id != null)
  const deviceUniqueIds = backendTargets
    .map((d) => d.uniqueId)
    .filter((id): id is string => !!id)
  /** 设备展示行：调用方标签优先，缺省取解析到的真实设备名 */
  const displayedDeviceLabels =
    deviceLabels.length > 0
      ? deviceLabels
      : backendTargets.map((d) => d.name).filter((n): n is string => !!n)

  // 时长兜底：调用方（用例音频卡/全局噪声）未带时长时按文件名回查音频库
  useEffect(() => {
    setResolvedDuration(null)
    if (audioId == null) return
    if (durationHint != null && durationHint > 0) return
    let cancelled = false
    void fetchAudioDuration(Number(audioId), audioName ?? null)
      .then((value) => {
        if (!cancelled) setResolvedDuration(value)
      })
      .catch(() => {
        /* 回查失败不阻断播放，进度条按已知信息展示 */
      })
    return () => {
      cancelled = true
    }
  }, [audioId, audioName, durationHint])

  // 音频元素生命周期（浏览器播放载体；加载/播放/seek 共用一个实例）
  useEffect(() => {
    const el = new Audio()
    el.preload = 'metadata'
    el.crossOrigin = 'anonymous'
    const onMetadata = () => {
      if (Number.isFinite(el.duration) && el.duration > 0) setDuration(el.duration)
    }
    const onTime = () => setCurrent(el.currentTime)
    const onEnded = () => {
      setPlaying(false)
      setCurrent(0)
    }
    const onError = () => {
      setError('音频加载失败，请确认音频文件存在且格式有效')
      setPlaying(false)
    }
    el.addEventListener('loadedmetadata', onMetadata)
    el.addEventListener('timeupdate', onTime)
    el.addEventListener('ended', onEnded)
    el.addEventListener('error', onError)
    audioRef.current = el
    return () => {
      el.pause()
      el.removeEventListener('loadedmetadata', onMetadata)
      el.removeEventListener('timeupdate', onTime)
      el.removeEventListener('ended', onEnded)
      el.removeEventListener('error', onError)
      el.removeAttribute('src')
      el.load()
      audioRef.current = null
    }
  }, [])

  // 浏览器播放：取真实流地址并装载（V9.7.31 契约 JSON 预签名 URL）
  useEffect(() => {
    if (mode !== 'frontend' || audioId == null) return
    let cancelled = false
    setError(null)
    // 音频库时长先占位；loadedmetadata 到达后用流真实时长覆盖（回查结果不重载流，见下方同步 effect）
    setDuration(durationHint != null && durationHint > 0 ? durationHint : 0)
    setCurrent(0)
    setPlaying(false)
    void stream(Number(audioId))
      .then((url) => {
        if (cancelled || !audioRef.current) return
        audioRef.current.src = url
        return audioRef.current.load()
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '获取音频流失败')
      })
    return () => {
      cancelled = true
    }
  }, [mode, audioId, durationHint])

  // 浏览器播放：回查到的时长只填补显示（流 metadata 已到达时以流为准，不重载流）
  useEffect(() => {
    if (mode !== 'frontend') return
    if (resolvedDuration == null) return
    setDuration((prev) => (prev > 0 ? prev : resolvedDuration))
  }, [mode, resolvedDuration])

  // 实验室播放：设备端播放无浏览器流，总时长取音频库时长（durationHint/回查兜底），进度按墙钟推进
  useEffect(() => {
    if (mode !== 'backend') return
    setDuration(hint != null && hint > 0 ? hint : 0)
    setCurrent(offset > 0 ? offset : 0)
  }, [mode, audioId, hint, offset])

  // 实验室播放：进度按墙钟推进（offset 为起点；已知总时长时到点自动停止）
  useEffect(() => {
    if (mode !== 'backend') return
    if (!playing) return
    const start = performance.now()
    const base = offset > 0 ? offset : 0
    const total = hint != null && hint > 0 ? hint : 0
    const timer = window.setInterval(() => {
      const next = base + (performance.now() - start) / 1000
      if (total > 0 && next >= total) {
        window.clearInterval(timer)
        setPlaying(false)
        setCurrent(0)
        if (audioId != null) void stopPreview(Number(audioId))
        return
      }
      setCurrent(next)
    }, 250)
    return () => window.clearInterval(timer)
  }, [mode, playing, offset, hint, audioId])

  /** 浏览器播放：真正播放/暂停当前音频元素 */
  const toggleFrontend = async () => {
    const el = audioRef.current
    if (!el || !el.src) return
    if (playing) {
      el.pause()
      setPlaying(false)
      return
    }
    setError(null)
    try {
      await el.play()
      setPlaying(true)
    } catch {
      setError('音频播放失败，请检查音频文件是否有效')
    }
  }

  /** 实验室播放：通知后端设备输出（按用例配置的播放设备发送） */
  const startBackend = async () => {
    if (audioId == null) return
    setError(null)
    const result = await preview(Number(audioId), {
      playbackDeviceId: playbackDeviceIds[0] ?? null,
      playbackDeviceIds,
      deviceUniqueIds,
      spl: spl ?? 65,
      offset: offset > 0 ? offset : undefined,
    })
    if (!result.success) {
      setError(result.message ?? '实验室播放启动失败')
      return
    }
    setCurrent(offset > 0 ? offset : 0)
    setPlaying(true)
  }

  const stopBackend = async () => {
    setPlaying(false)
    setCurrent(0)
    if (audioId == null) return
    await stopPreview(Number(audioId))
  }

  const togglePlay = () => {
    if (mode === 'frontend') void toggleFrontend()
    else if (playing) {
      setPlaying(false)
      if (audioId != null) void stopPreview(Number(audioId))
    } else void startBackend()
  }

  const stop = () => {
    if (mode === 'frontend') {
      const el = audioRef.current
      if (el) {
        el.pause()
        el.currentTime = 0
      }
      setPlaying(false)
      setCurrent(0)
    } else void stopBackend()
  }

  /** 进度 seek（浏览器播放直接跳转；实验室播放由后端以新 offset 重发） */
  const onSeek = (value: number | readonly number[]) => {
    const target = Array.isArray(value) ? (value[0] ?? 0) : value
    if (mode === 'frontend') {
      const el = audioRef.current
      if (el && Number.isFinite(el.duration) && el.duration > 0) {
        el.currentTime = Math.min(target, el.duration)
        setCurrent(el.currentTime)
      }
    } else if (audioId != null) {
      setCurrent(target)
      void preview(Number(audioId), {
        playbackDeviceId: playbackDeviceIds[0] ?? null,
        playbackDeviceIds,
        deviceUniqueIds,
        spl: spl ?? 65,
        offset: target,
      })
    }
  }

  const realDuration = duration > 0 ? duration : Math.max(current, 0)

  return (
    <div className='space-y-4'>
      {audioName && (
        <p className='text-muted-foreground truncate text-sm' title={audioName}>
          {audioName}
        </p>
      )}
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
        max={Math.max(realDuration, 1)}
        value={Math.min(current, realDuration)}
        aria-label='播放进度'
        onValueChange={onSeek}
      />
      <p
        data-testid='player-time'
        className='text-muted-foreground font-mono text-xs tabular-nums'
      >
        {formatClock(current)} / {formatClock(realDuration)}
      </p>

      <div className='flex flex-wrap items-center gap-2'>
        <Button
          size='sm'
          className='h-8 gap-1.5'
          aria-label={playing ? '暂停' : '播放'}
          disabled={audioId == null}
          onClick={togglePlay}
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
          onClick={stop}
        >
          <Square aria-hidden='true' className='size-4' />
          停止
        </Button>
      </div>

      <div className='space-y-1.5 rounded-lg border p-3'>
        <p className='text-muted-foreground text-xs font-medium'>
          播放设备{mode === 'backend' ? '（实验室播放）' : '（浏览器播放）'}
        </p>
        {displayedDeviceLabels.length === 0 ? (
          <p className='text-muted-foreground/70 text-sm'>
            {mode === 'backend'
              ? deviceIds.length > 0
                ? '未匹配到用例配置的播放设备记录，后端将按默认设备播放'
                : '未配置播放设备'
              : '浏览器直接播放，无需指定设备'}
          </p>
        ) : (
          displayedDeviceLabels.map((d) => (
            <p key={d} className='flex items-center gap-1.5 text-sm'>
              <span className='text-primary'>✓</span>
              {d}
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
