/**
 * 音频播放器（11_用例域.md §5.2，Dialog `sm:max-w-lg` 内容态面板）。
 * 进度条（Slider 点击/拖拽定位）+ 时间 `{current}/{duration}` tabular-nums +
 * 控制钮（播放/暂停、停止）+ 播放设备信息区（勾选设备「✓ {设备名}」）+ 错误条（Alert destructive 可关闭）。
 * 由 AudioPreviewConfigDialog 内嵌渲染（「开始试听」后切换 stage 呈现）。
 *
 * 一个播放器支持两种播放源（二选一 props，INT-1534 返工并线）：
 * 1) 用例试听（`preview` + `caseItem`，INT-1534）：用例行「预览音频」→ 配置态已发
 *    POST /testcases/{id}/preview，响应 audio_stream_urls 为多轮音频流，按轮次顺序连播；
 *    实验室播放的停止/续播/定位走 POST /testcases/{id}/stop_preview 与带 offset 重发 preview。
 * 2) 音频库/全局噪声试听（`audioId`，INT-1424）：浏览器播放 GET /audios/{id}/stream 取真实流，
 *    实验室播放 POST /audios/{id}/preview / stop-preview，设备取 playback_device_ids + device_unique_ids。
 * 两种源都不再有 42s 假时长、1s 假进度或写死设备。
 */
import { Pause, Play, Square, TriangleAlert, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { usePlaybackDevices } from '@/application/devices/use-devices'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { casePlaybackDevicesFromConfig } from '@/domain/lib/testcase-round-config'
import type {
  PreviewPlaybackMode,
  TestCaseListItem,
  TestCasePreview,
} from '@/domain/models/testCase'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  fetchAudioDuration,
  preview as previewAudio,
  stopPreview as stopAudioPreview,
  stream as streamAudio,
} from '@/infrastructure/api/audios-api'
import {
  previewTestCase,
  stopTestCasePreview,
} from '@/infrastructure/api/testcases-api'

const formatClock = (s: number): string => {
  const value = Number.isFinite(s) && s > 0 ? Math.floor(s) : 0
  const m = Math.floor(value / 60)
  const sec = value % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

/** `<audio>` 错误码 → 中文文案（V9.7.10 AudioPlayerModal.handleError 逐条平移） */
function audioErrorMessage(code: number | undefined): string {
  switch (code) {
    case 1:
      return '音频文件未找到，请检查文件是否存在'
    case 2:
      return '音频格式不支持，请联系管理员'
    case 3:
      return '音频解码错误，可能是文件损坏'
    case 4:
      return '音频格式不支持或服务器返回错误(400)'
    default:
      return '音频播放失败，请重试'
  }
}

interface BasePlayerProps {
  mode: PreviewPlaybackMode
  /** 返回试听配置（§5.2 播放器→配置双向切换；返回前停止放音） */
  onBack: () => void
}

/** 用例试听源（INT-1534：用例行「预览音频」→ POST /testcases/{id}/preview） */
export interface CasePreviewPlayerProps extends BasePlayerProps {
  /** 配置态 POST /testcases/{id}/preview 的真实响应（多轮为 audioStreamUrls 连播） */
  preview: TestCasePreview
  /** 用例（播放设备区取 config.rounds[].audios 真实配置） */
  caseItem: TestCaseListItem
  /** 配置态提交的偏移量（实验室播放的进度基准） */
  startOffset?: number
}

/** 音频库/全局噪声试听源（INT-1424：GET /audios/{id}/stream + POST /audios/{id}/preview） */
export interface AudioLibraryPlayerProps extends BasePlayerProps {
  /** 音频 id（null 时不发起播放，仅展示空态） */
  audioId: number | string | null
  /** 音频文件名（标题区展示） */
  audioName?: string | null
  /** 播放设备展示标签（实验室播放=用例配置设备名列表；浏览器可为空） */
  deviceLabels?: string[]
  /** 播放设备记录 id（用例配置的 playback_device_id / 全局噪声 deviceIds）：
   *  实验室播放解析成 playback_device_ids + device_unique_ids 随请求发送 */
  deviceIds?: string[]
  /** 实验室播放声压级（dB） */
  spl?: number | null
  /** 实验室播放起点偏移（秒） */
  offset?: number
  /** 音频库已知总时长（秒）：浏览器播放先作占位、metadata 到达后覆盖；
   *  实验室播放无浏览器流，总时长靠它兜底 */
  durationHint?: number | null
}

export type AudioPlayerPanelProps =
  | CasePreviewPlayerProps
  | AudioLibraryPlayerProps

const sum = (values: number[]): number =>
  values.reduce((total, value) => total + value, 0)

export function AudioPlayerPanel(props: AudioPlayerPanelProps) {
  const { mode, onBack } = props
  const isBackend = mode === 'backend'
  /** 播放源二选一：带 preview 即用例试听源，否则音频库试听源 */
  const isCaseSource = 'preview' in props
  const casePreview = isCaseSource
    ? (props as CasePreviewPlayerProps).preview
    : null
  const caseItem = isCaseSource
    ? (props as CasePreviewPlayerProps).caseItem
    : null
  const libProps = isCaseSource ? null : (props as AudioLibraryPlayerProps)
  const libAudioId = libProps?.audioId ?? null
  const libAudioName = libProps?.audioName ?? null
  const libSpl = libProps?.spl ?? 65
  const libDurationHint = libProps?.durationHint ?? null
  const libDeviceIds = libProps?.deviceIds
  const libDeviceLabels = libProps?.deviceLabels
  const startOffset = isCaseSource
    ? ((props as CasePreviewPlayerProps).startOffset ?? 0)
    : (libProps?.offset ?? 0)

  /** 用例源的音频流（配置态 preview 响应即带多轮地址） */
  const caseClips = useMemo(() => {
    if (!casePreview) return []
    if (casePreview.audioStreamUrls.length > 0) return casePreview.audioStreamUrls
    return casePreview.audioStreamUrl ? [casePreview.audioStreamUrl] : []
  }, [casePreview])

  /** 音频库源：浏览器播放地址由 GET /audios/{id}/stream 异步取回 */
  const [libClip, setLibClip] = useState<string | null>(null)
  const clips = isCaseSource ? caseClips : libClip ? [libClip] : []

  /** 播放设备：用例源取 config 真实设备；音频库源按 id 解析设备记录（名称 + 唯一 id） */
  const devicesQuery = usePlaybackDevices()
  const libDeviceTargets = useMemo(() => {
    const all = devicesQuery.data ?? []
    return (libDeviceIds ?? []).map((raw) => {
      const numeric = Number(raw)
      const hit = Number.isFinite(numeric)
        ? all.find((device) => Number(device.id) === numeric)
        : undefined
      return {
        id: hit ? Number(hit.id) : Number.isFinite(numeric) ? numeric : null,
        uniqueId: hit?.deviceUniqueId ?? null,
        name: hit?.name ?? null,
      }
    })
  }, [libDeviceIds, devicesQuery.data])
  const libPlaybackDeviceIds = libDeviceTargets
    .map((device) => device.id)
    .filter((id): id is number => id != null)
  const libDeviceUniqueIds = libDeviceTargets
    .map((device) => device.uniqueId)
    .filter((id): id is string => !!id)

  const deviceRows = isCaseSource
    ? isBackend
      ? casePlaybackDevicesFromConfig(caseItem?.config).map(
          (device) => device.name
        )
      : []
    : (libDeviceLabels?.length ?? 0) > 0
      ? (libDeviceLabels ?? [])
      : libDeviceTargets
          .map((device) => device.name)
          .filter((name): name is string => !!name)
  const emptyDeviceText = isCaseSource
    ? isBackend
      ? '该用例未配置播放设备'
      : '本机扬声器直接输出'
    : isBackend
      ? (libDeviceIds?.length ?? 0) > 0
        ? '未匹配到用例配置的播放设备记录，后端将按默认设备播放'
        : '未配置播放设备'
      : '浏览器直接播放，无需指定设备'

  const audioRef = useRef<HTMLAudioElement | null>(null)
  /** 实验室播放的进度基准（墙钟起点对应的媒体秒数） */
  const clockBaseRef = useRef(startOffset)
  const clockStartRef = useRef<number | null>(null)
  /** 拖动进度条期间冻结墙钟推进，松手再按目标位置重发试听 */
  const seekingRef = useRef(false)
  /** 多轮切段后待应用的段内定位（metadata 到达前 el.currentTime 赋值会被忽略） */
  const pendingSeekRef = useRef<number | null>(null)

  const [clipIndex, setClipIndex] = useState(0)
  /** 各轮音频的真实时长（按 metadata 逐一记录；用于累计定位与总时长兜底） */
  const [clipDurations, setClipDurations] = useState<number[]>([])
  const [current, setCurrent] = useState(
    isCaseSource && isBackend ? startOffset : 0
  )
  /** 单段源（音频库/单轮用例）的时长；多轮用例以 clipDurations 累计为准 */
  const [duration, setDuration] = useState(0)
  /** 音频库源时长回查（调用方未带 durationHint 时） */
  const [resolvedDuration, setResolvedDuration] = useState<number | null>(null)
  // 「开始试听」后用例源直接进入播放态（浏览器起播 / 实验室已由网关放音，进度跟墙钟走）；
  // 音频库源由用户在播放器里点「播放」起播（INT-1424 口径）
  const [playing, setPlayingState] = useState(
    isCaseSource && (isBackend || caseClips.length > 0)
  )
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const playingRef = useRef(playing)
  /** 卸载时延后发出的停止定时器（重新挂载即取消，见下方 cleanup） */
  const stopTimerRef = useRef<number | null>(null)
  /** 播放态写入同步更新 ref：卸载 cleanup 依 ref 判断是否仍需停后端，
   *  否则「返回试听配置」与 cleanup 各 stop 一次（INT-1534 P3-1） */
  const setPlaying = useCallback((value: boolean) => {
    playingRef.current = value
    setPlayingState(value)
  }, [])

  /** 已知总时长：用例源取 preview.duration（多轮为全部音频之和），音频库源取时长兜底 */
  const knownTotal = isCaseSource
    ? casePreview?.duration != null && casePreview.duration > 0
      ? casePreview.duration
      : 0
    : libDurationHint != null && libDurationHint > 0
      ? libDurationHint
      : resolvedDuration != null && resolvedDuration > 0
        ? resolvedDuration
        : 0
  const loadedSum = sum(clipDurations)
  const totalDuration = isCaseSource
    ? knownTotal > 0
      ? knownTotal
      : loadedSum
    : duration > 0
      ? duration
      : loadedSum
  /** 已播过的轮次累计时长（尚未加载 metadata 的轮次按 0 计） */
  const playedPrefix = sum(clipDurations.slice(0, clipIndex))
  const position = isBackend ? current : playedPrefix + current

  /** 音频库源：浏览器播放地址（GET /audios/{id}/stream） */
  useEffect(() => {
    setLibClip(null)
    if (isCaseSource || isBackend || libAudioId == null) return
    let cancelled = false
    setError(null)
    void streamAudio(Number(libAudioId))
      .then((url) => {
        if (!cancelled) setLibClip(url)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.userMessage : '获取音频流失败')
        }
      })
    return () => {
      cancelled = true
    }
  }, [isCaseSource, isBackend, libAudioId])

  /** 音频库源：时长兜底（调用方未带 durationHint 时按 id/文件名回查音频库） */
  useEffect(() => {
    setResolvedDuration(null)
    if (isCaseSource || libAudioId == null) return
    if (libDurationHint != null && libDurationHint > 0) return
    let cancelled = false
    void fetchAudioDuration(Number(libAudioId), libAudioName)
      .then((value) => {
        if (!cancelled) setResolvedDuration(value)
      })
      .catch(() => {
        /* 回查失败不阻断播放，进度条按已知信息展示 */
      })
    return () => {
      cancelled = true
    }
  }, [isCaseSource, libAudioId, libAudioName, libDurationHint])

  /** 音频库源：已知时长先占位（metadata 到达后以流为准）；实验室播放起点跟随 offset */
  useEffect(() => {
    if (isCaseSource) return
    setDuration(knownTotal)
    if (isBackend) setCurrent(startOffset > 0 ? startOffset : 0)
  }, [isCaseSource, isBackend, knownTotal, startOffset])

  /** 用例源浏览器播放但后端没给流地址 → 明确错误态（不假装在播） */
  useEffect(() => {
    if (!isCaseSource) return
    if (!isBackend && caseClips.length === 0) {
      setError('未获取到音频播放地址，无法播放')
    }
  }, [isCaseSource, isBackend, caseClips.length])

  /** 停止实验室放音（用例源走 stop_preview，音频库源走 stop-preview；失败不打断 UI 停止动作） */
  const stopBackend = useCallback(async (): Promise<void> => {
    if (isCaseSource) {
      if (!caseItem) return
      await stopTestCasePreview(caseItem.id).catch(() => {})
      return
    }
    if (libAudioId == null) return
    await stopAudioPreview(Number(libAudioId)).catch(() => {})
  }, [isCaseSource, caseItem, libAudioId])

  /** 实验室播放续播/定位：重新发起试听并携带 offset */
  const startBackend = useCallback(
    async (offset: number): Promise<boolean> => {
      setPending(true)
      try {
        if (isCaseSource) {
          if (!caseItem) return false
          const result = await previewTestCase(caseItem.id, {
            offset,
            previewType: 'backend',
            playbackMode: 'backend',
          })
          if (result.duration != null && result.duration > 0) {
            setDuration(result.duration)
          }
        } else {
          if (libAudioId == null) return false
          const result = await previewAudio(Number(libAudioId), {
            playbackDeviceId: libPlaybackDeviceIds[0] ?? null,
            playbackDeviceIds: libPlaybackDeviceIds,
            deviceUniqueIds: libDeviceUniqueIds,
            spl: libSpl,
            offset: offset > 0 ? offset : undefined,
          })
          if (!result.success) {
            setError(result.message ?? '实验室播放启动失败')
            return false
          }
        }
        clockBaseRef.current = offset
        setError(null)
        return true
      } catch (err) {
        setError(err instanceof ApiError ? err.userMessage : '音频播放失败，请重试')
        return false
      } finally {
        setPending(false)
      }
    },
    [
      isCaseSource,
      caseItem,
      libAudioId,
      libPlaybackDeviceIds,
      libDeviceUniqueIds,
      libSpl,
    ]
  )

  /** 实验室内播放进度：按墙钟推算（时长未知时只推进时间戳，不提前结束） */
  useEffect(() => {
    if (!isBackend || !playing) return
    clockStartRef.current = performance.now()
    const timer = window.setInterval(() => {
      const startedAt = clockStartRef.current
      if (startedAt == null) return
      const next = clockBaseRef.current + (performance.now() - startedAt) / 1000
      if (totalDuration > 0 && next >= totalDuration) {
        setCurrent(totalDuration)
        setPlaying(false)
        void stopBackend()
        return
      }
      if (!seekingRef.current) setCurrent(next)
    }, 200)
    return () => {
      window.clearInterval(timer)
      const startedAt = clockStartRef.current
      if (startedAt != null) {
        clockBaseRef.current += (performance.now() - startedAt) / 1000
      }
      clockStartRef.current = null
    }
  }, [isBackend, playing, totalDuration, stopBackend])

  /** 浏览器播放：起播/暂停 + 多轮切段后自动接续 */
  useEffect(() => {
    if (isBackend) return
    const el = audioRef.current
    if (!el) return
    if (!playing) {
      el.pause()
      return
    }
    const promise = el.play()
    if (promise) {
      promise.catch((err: unknown) => {
        // 浏览器自动播放策略拦截不算播放失败：退回暂停态，等用户点「播放」起播
        if ((err as DOMException | undefined)?.name === 'NotAllowedError') {
          setPlaying(false)
          return
        }
        setError('音频播放失败，请检查音频文件是否有效')
        setPlaying(false)
      })
    }
  }, [isBackend, playing, clipIndex, clips.length])

  /** 关闭/切回配置时停止放音（实验室内设备端放音必须显式停）。
   *  停止延后到下一拍并在重新挂载时取消：StrictMode 开发态挂载会先跑一次 cleanup，
   *  立即 stop 会把刚启动的实验室放音停掉（INT-1534 P3-1）。 */
  useEffect(() => {
    if (stopTimerRef.current != null) {
      window.clearTimeout(stopTimerRef.current)
      stopTimerRef.current = null
    }
    return () => {
      if (playingRef.current && isBackend) {
        stopTimerRef.current = window.setTimeout(() => {
          stopTimerRef.current = null
          void stopBackend()
        }, 0)
      }
      const el = audioRef.current
      if (el) el.pause()
    }
  }, [isBackend, stopBackend])

  const backToConfig = () => {
    // 先停设备放音并把播放态（含 ref）落下，卸载 cleanup 不再重复 stop（INT-1534 P3-1）
    if (isBackend && playingRef.current) void stopBackend()
    setPlaying(false)
    const el = audioRef.current
    if (el) el.pause()
    onBack()
  }

  const handleTogglePlay = async () => {
    if (pending) return
    if (!isBackend) {
      if (clips.length === 0) return
      if (!playing && totalDuration > 0 && position >= totalDuration) {
        // 播完后再点播放：从头开始
        setClipIndex(0)
        setClipDurations([])
        setCurrent(0)
        clockBaseRef.current = 0
      }
      setPlaying(!playing)
      return
    }
    if (playing) {
      // 暂停：先等设备端停下（与后续 preview 串行，避免 stop 后到把新放音停掉）
      await stopBackend()
      setPlaying(false)
      return
    }
    const restart = totalDuration > 0 && current >= totalDuration
    const from = restart ? 0 : current
    if (restart) {
      clockBaseRef.current = 0
      setCurrent(0)
    }
    if (!(await startBackend(from))) return
    setPlaying(true)
  }

  const handleStop = async () => {
    if (isBackend) {
      const wasPlaying = playing
      setPlaying(false)
      clockBaseRef.current = 0
      setCurrent(0)
      if (wasPlaying) await stopBackend()
      return
    }
    const el = audioRef.current
    if (el) {
      el.pause()
      el.currentTime = 0
    }
    setPlaying(false)
    setClipIndex(0)
    setClipDurations([])
    setCurrent(0)
  }

  /** 多轮用例：把「总进度目标」换算成「第几轮 + 段内秒数」 */
  const locateClip = (target: number): { index: number; local: number } => {
    if (clips.length <= 1) return { index: 0, local: target }
    let remaining = target
    for (let index = 0; index < clips.length; index += 1) {
      const clipDuration = clipDurations[index] ?? 0
      if (index === clips.length - 1) {
        return { index, local: Math.max(0, remaining) }
      }
      if (clipDuration > 0 && remaining < clipDuration) {
        return { index, local: remaining }
      }
      if (clipDuration <= 0) {
        // 后续轮次时长未知（未加载过 metadata）：停留在当前段内定位
        return { index: Math.max(index, clipIndex), local: Math.max(0, remaining) }
      }
      remaining -= clipDuration
    }
    return { index: clips.length - 1, local: Math.max(0, remaining) }
  }

  /** 拖动中：只更新显示位置并即时 seek（实验室播放等松手再重发） */
  const handleSeekChange = (value: number) => {
    const target = Math.max(
      0,
      Math.min(value, totalDuration > 0 ? totalDuration : value)
    )
    seekingRef.current = true
    if (isBackend) {
      setCurrent(target)
      return
    }
    const el = audioRef.current
    if (!el) return
    const located = locateClip(target)
    if (located.index === clipIndex) {
      el.currentTime = located.local
      setCurrent(located.local)
      return
    }
    pendingSeekRef.current = located.local
    setClipIndex(located.index)
    setCurrent(located.local)
  }

  /** 松手定位：实验室播放先等设备端停下，再按目标偏移重发试听（V9.7.10 stopDrag 串行口径） */
  const handleSeekCommit = async (value: number) => {
    seekingRef.current = false
    const target = Math.max(
      0,
      Math.min(value, totalDuration > 0 ? totalDuration : value)
    )
    if (!isBackend) {
      const el = audioRef.current
      if (!el) return
      const located = locateClip(target)
      if (located.index === clipIndex) {
        el.currentTime = located.local
        setCurrent(located.local)
      } else {
        pendingSeekRef.current = located.local
        setClipIndex(located.index)
        setCurrent(located.local)
      }
      return
    }
    clockBaseRef.current = target
    setCurrent(target)
    if (!playing) return
    setPlaying(false)
    await stopBackend()
    if (await startBackend(target)) setPlaying(true)
  }

  const maxDuration = totalDuration > 0 ? totalDuration : 1
  // 时长未知（实验室播放后端只回 0）时进度条停在起点并禁用，避免看起来已播满
  const sliderValue =
    totalDuration > 0 ? Math.max(0, Math.min(position, totalDuration)) : 0

  return (
    <div className='space-y-4'>
      {libAudioName && (
        <p className='text-muted-foreground truncate text-sm' title={libAudioName}>
          {libAudioName}
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

      {!isBackend && clips.length > 0 && (
        <audio
          ref={audioRef}
          src={clips[Math.min(clipIndex, clips.length - 1)]}
          preload='metadata'
          data-testid='case-preview-audio'
          onLoadedMetadata={(e) => {
            const el = e.currentTarget
            const clipDuration =
              Number.isFinite(el.duration) && el.duration > 0 ? el.duration : 0
            setClipDurations((previous) => {
              const next = [...previous]
              next[clipIndex] = clipDuration
              return next
            })
            if (!isCaseSource && clipDuration > 0) setDuration(clipDuration)
            const seekTarget = pendingSeekRef.current
            if (seekTarget != null) {
              el.currentTime = seekTarget
              pendingSeekRef.current = null
            }
            setCurrent(el.currentTime)
          }}
          onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
          onEnded={() => {
            const clipDuration = clipDurations[clipIndex] ?? 0
            if (clipIndex + 1 < clips.length) {
              setClipIndex((index) => index + 1)
              setCurrent(0)
              return
            }
            setPlaying(false)
            setCurrent(clipDuration)
          }}
          onError={(e) => {
            setError(audioErrorMessage(e.currentTarget.error?.code))
            setPlaying(false)
          }}
        />
      )}

      <Slider
        min={0}
        max={maxDuration}
        step={0.1}
        value={sliderValue}
        aria-label='播放进度'
        disabled={totalDuration <= 0 && isBackend}
        onValueChange={(value) => {
          const next = Array.isArray(value) ? value[0] : value
          handleSeekChange(next)
        }}
        onValueCommitted={(value) => {
          const next = Array.isArray(value) ? value[0] : value
          void handleSeekCommit(next)
        }}
      />
      <p
        data-testid='player-time'
        className='text-muted-foreground font-mono text-xs tabular-nums'
      >
        {formatClock(position)} /{' '}
        {totalDuration > 0 ? formatClock(totalDuration) : '--:--'}
        {!isBackend && clips.length > 1
          ? ` · 第 ${Math.min(clipIndex + 1, clips.length)}/${clips.length} 轮`
          : ''}
      </p>

      <div className='flex flex-wrap items-center gap-2'>
        <Button
          size='sm'
          className='h-8 gap-1.5'
          aria-label={playing ? '暂停' : '播放'}
          disabled={pending || (!isBackend && clips.length === 0)}
          onClick={handleTogglePlay}
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
          disabled={pending}
          onClick={handleStop}
        >
          <Square aria-hidden='true' className='size-4' />
          停止
        </Button>
      </div>

      <div className='space-y-1.5 rounded-lg border p-3'>
        <p className='text-muted-foreground text-xs font-medium'>
          播放设备{mode === 'backend' ? '（实验室播放）' : '（浏览器播放）'}
        </p>
        {deviceRows.length === 0 ? (
          <p className='text-muted-foreground/70 text-sm'>{emptyDeviceText}</p>
        ) : (
          deviceRows.map((device) => (
            <p key={device} className='flex items-center gap-1.5 text-sm'>
              <span className='text-primary'>✓</span>
              {device}
            </p>
          ))
        )}
      </div>

      <div className='flex justify-end'>
        <Button variant='ghost' size='sm' onClick={backToConfig}>
          返回试听配置
        </Button>
      </div>
    </div>
  )
}
