/**
 * 音频时间轴（15_报告域.md §3.5.7，AudioTimelineVisualization 平移）。
 * normalizeAudioItem 归一 audioList → 分段时间轴可视化（mock：按 play_order 等分展示）。
 * onPlay 提供时各音频段为可点击按钮，点击播放对应「输入音频」。
 */
import type { ReportAudioItem } from '@/domain/models/report'

interface AudioTimelineProps {
  audioList: ReportAudioItem[]
  /** 点击时间轴音频段播放对应输入音频；缺省为纯展示时间轴 */
  onPlay?: (audio: ReportAudioItem) => void
}

export function AudioTimeline({ audioList, onPlay }: AudioTimelineProps) {
  if (!audioList || audioList.length === 0) {
    return (
      <div className='text-muted-foreground flex h-14 items-center justify-center rounded-lg border text-xs'>
        暂无音频时间轴数据
      </div>
    )
  }

  const total = audioList.length
  return (
    <div className='overflow-hidden rounded-lg border p-3'>
      <p className='text-muted-foreground text-xs font-medium'>音频时间轴</p>
      {onPlay && (
        <p className='text-muted-foreground mt-0.5 text-[10px]'>点击音频段播放输入音频</p>
      )}
      <div className='relative mt-2 flex h-10 items-center gap-1'>
        {audioList.map((audio, index) => {
          const name = audio.audio_name ?? `音频 ${audio.audio_id ?? index + 1}`
          const baseCls =
            'flex h-full min-w-0 flex-1 flex-col items-center justify-center overflow-hidden rounded-sm text-center'
          const inner = (
            <>
              <span className='w-full truncate px-1 text-[10px] leading-tight'>{name}</span>
              <span className='text-[9px] opacity-70'>{index + 1}</span>
            </>
          )
          if (!onPlay) {
            return (
              <div
                key={String(audio.audio_id)}
                className={`${baseCls} bg-primary/30`}
                title={`${name} · SPL ${audio.spl ?? '—'}dB`}
              >
                {inner}
              </div>
            )
          }
          return (
            <button
              key={String(audio.audio_id)}
              type='button'
              className={`${baseCls} bg-primary/30 cursor-pointer transition-colors hover:bg-primary/50`}
              title={`${name} · 点击播放输入音频`}
              onClick={() => onPlay(audio)}
            >
              {inner}
            </button>
          )
        })}
      </div>
      <div className='text-muted-foreground mt-1 flex justify-between text-[10px] font-mono tabular-nums'>
        <span>0s</span>
        <span>{total * 5}s</span>
      </div>
    </div>
  )
}
