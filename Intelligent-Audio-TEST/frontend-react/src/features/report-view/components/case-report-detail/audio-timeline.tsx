/**
 * 音频时间轴（15_报告域.md §3.5.7，AudioTimelineVisualization 平移）。
 * 优先按 report_service 下发的 timelineStart/timelineEnd 按比例绘制（与播放口径一致）；
 * 旧数据缺时间轴字段时回退为按 play_order 等分展示。
 * onPlay 提供时各音频段为可点击按钮，点击播放对应「输入音频」。
 */
import type { CSSProperties } from 'react'

import type { ReportAudioItem } from '@/domain/models/report'

interface AudioTimelineProps {
  audioList: ReportAudioItem[]
  /** 点击时间轴音频段播放对应输入音频；缺省为纯展示时间轴 */
  onPlay?: (audio: ReportAudioItem) => void
}

/** 等分兜底时每段假定时长（秒），仅用于刻度展示 */
const FALLBACK_SECONDS_PER_SEGMENT = 5

function finiteOrUndefined(value: number | undefined): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  return value
}

/** 真实时间轴总时长；任一音频缺有效 timelineStart/timelineEnd 时返回 null（走等分兜底） */
function resolveTimelineTotal(audioList: ReportAudioItem[]): number | null {
  let total = 0
  for (const audio of audioList) {
    const start = finiteOrUndefined(audio.timelineStart)
    const end = finiteOrUndefined(audio.timelineEnd)
    if (start === undefined || end === undefined || end <= start) return null
    total = Math.max(total, end)
  }
  return total > 0 ? total : null
}

function formatSeconds(value: number): string {
  const rounded = Math.round(value * 10) / 10
  if (Number.isInteger(rounded)) return String(rounded)
  return rounded.toFixed(1)
}

interface AudioSegmentProps {
  audio: ReportAudioItem
  index: number
  className: string
  style?: CSSProperties
  onPlay?: (audio: ReportAudioItem) => void
}

function AudioSegment(props: AudioSegmentProps) {
  const name = props.audio.audio_name ?? `音频 ${props.audio.audio_id ?? props.index + 1}`
  const content = (
    <>
      <span className='w-full truncate px-1 text-[10px] leading-tight'>{name}</span>
      <span className='text-[9px] opacity-70'>{props.index + 1}</span>
    </>
  )
  if (!props.onPlay) {
    return (
      <div
        className={props.className}
        style={props.style}
        title={`${name} · SPL ${props.audio.spl ?? '—'}dB`}
      >
        {content}
      </div>
    )
  }
  return (
    <button
      type='button'
      className={`${props.className} cursor-pointer transition-colors hover:bg-primary/50`}
      style={props.style}
      title={`${name} · 点击播放输入音频`}
      onClick={() => props.onPlay?.(props.audio)}
    >
      {content}
    </button>
  )
}

export function AudioTimeline(props: AudioTimelineProps) {
  const audioList = props.audioList ?? []
  if (audioList.length === 0) {
    return (
      <div className='text-muted-foreground flex h-14 items-center justify-center rounded-lg border text-xs'>
        暂无音频时间轴数据
      </div>
    )
  }

  const timelineTotal = resolveTimelineTotal(audioList)
  const totalSeconds = timelineTotal ?? audioList.length * FALLBACK_SECONDS_PER_SEGMENT

  return (
    <div className='overflow-hidden rounded-lg border p-3'>
      <p className='text-muted-foreground text-xs font-medium'>音频时间轴</p>
      {props.onPlay && (
        <p className='text-muted-foreground mt-0.5 text-[10px]'>点击音频段播放输入音频</p>
      )}
      {timelineTotal === null ? (
        <div className='relative mt-2 flex h-10 items-center gap-1'>
          {audioList.map((audio, index) => (
            <AudioSegment
              key={String(audio.audio_id)}
              audio={audio}
              index={index}
              className='bg-primary/30 flex h-full min-w-0 flex-1 flex-col items-center justify-center overflow-hidden rounded-sm text-center'
              onPlay={props.onPlay}
            />
          ))}
        </div>
      ) : (
        <div className='relative mt-2 h-10 w-full' data-testid='audio-timeline-track'>
          {audioList.map((audio, index) => {
            const start = finiteOrUndefined(audio.timelineStart) ?? 0
            const end = finiteOrUndefined(audio.timelineEnd) ?? start
            const style: CSSProperties = {
              left: `${(start / timelineTotal) * 100}%`,
              width: `${((end - start) / timelineTotal) * 100}%`,
            }
            return (
              <AudioSegment
                key={String(audio.audio_id)}
                audio={audio}
                index={index}
                className='bg-primary/30 absolute top-0 flex h-full flex-col items-center justify-center overflow-hidden rounded-sm text-center'
                style={style}
                onPlay={props.onPlay}
              />
            )
          })}
        </div>
      )}
      <div className='text-muted-foreground mt-1 flex justify-between text-[10px] font-mono tabular-nums'>
        <span>0s</span>
        <span>{formatSeconds(totalSeconds)}s</span>
      </div>
    </div>
  )
}
