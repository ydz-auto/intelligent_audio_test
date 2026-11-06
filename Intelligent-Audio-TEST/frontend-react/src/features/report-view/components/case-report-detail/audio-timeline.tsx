/**
 * 音频时间轴（15_报告域.md §3.5.7，AudioTimelineVisualization 平移）。
 * normalizeAudioItem 归一 audioList → 分段时间轴可视化（mock：按 play_order 等分展示）。
 */
import type { ReportAudioItem } from '@/domain/models/report'

interface AudioTimelineProps {
  audioList: ReportAudioItem[]
}

export function AudioTimeline({ audioList }: AudioTimelineProps) {
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
      <div className='relative mt-2 flex h-10 items-center gap-1'>
        {audioList.map((audio, index) => (
          <div
            key={String(audio.audio_id)}
            // 纯展示时间轴分段（无点击行为，不用 cursor-pointer 伪可点；P3-8）
            className='bg-primary/30 flex h-full flex-1 flex-col items-center justify-center overflow-hidden rounded-sm text-center transition-colors'
            title={`${audio.audio_name ?? `音频 ${audio.audio_id}`} · SPL ${audio.spl ?? '—'}dB`}
          >
            <span className='px-1 text-[10px] leading-tight'>{index + 1}</span>
          </div>
        ))}
      </div>
      <div className='text-muted-foreground mt-1 flex justify-between text-[10px] font-mono tabular-nums'>
        <span>0s</span>
        <span>{total * 5}s</span>
      </div>
    </div>
  )
}
