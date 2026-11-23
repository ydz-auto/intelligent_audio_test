/**
 * 报告用例音频时间轴：优先按后端 timelineStart/timelineEnd 比例绘制，
 * 旧数据缺字段时等分兜底；点击段回调对应音频。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReportAudioItem } from '@/domain/models/report'

import { AudioTimeline } from '../audio-timeline'

const TIMED_AUDIOS: ReportAudioItem[] = [
  { audio_id: 11, audio_name: '第一段', spl: 70, timelineStart: 0, timelineEnd: 3 },
  { audio_id: 12, audio_name: '第二段', spl: 72, timelineStart: 3, timelineEnd: 6 },
]

describe('AudioTimeline 时间轴', () => {
  it('有真实 timeline 字段时按时间比例绘制各段并显示总时长', () => {
    render(<AudioTimeline audioList={TIMED_AUDIOS} />)

    expect(screen.getByTitle('第一段 · SPL 70dB')).toHaveStyle({ left: '0%', width: '50%' })
    expect(screen.getByTitle('第二段 · SPL 72dB')).toHaveStyle({ left: '50%', width: '50%' })
    expect(screen.getByText('6s')).toBeInTheDocument()
  })

  it('缺 timeline 字段时回退等分展示（每段 5 秒刻度）', () => {
    render(
      <AudioTimeline
        audioList={[
          { audio_id: 21, audio_name: '甲' },
          { audio_id: 22, audio_name: '乙' },
        ]}
      />
    )

    expect(screen.queryByTestId('audio-timeline-track')).toBeNull()
    expect(screen.getByTitle('甲 · SPL —dB')).toHaveClass('flex-1')
    expect(screen.getByTitle('乙 · SPL —dB')).toHaveClass('flex-1')
    expect(screen.getByText('10s')).toBeInTheDocument()
  })

  it('部分音频缺 timeline 字段时整体回退等分（不混用两种布局）', () => {
    render(
      <AudioTimeline
        audioList={[
          { audio_id: 31, audio_name: '有轴', timelineStart: 0, timelineEnd: 2 },
          { audio_id: 32, audio_name: '无轴' },
        ]}
      />
    )

    expect(screen.queryByTestId('audio-timeline-track')).toBeNull()
    expect(screen.getByText('10s')).toBeInTheDocument()
  })

  it('点击音频段回调对应音频', () => {
    const onPlay = vi.fn()
    render(<AudioTimeline audioList={TIMED_AUDIOS} onPlay={onPlay} />)

    fireEvent.click(screen.getByTitle('第二段 · 点击播放输入音频'))
    expect(onPlay).toHaveBeenCalledWith(TIMED_AUDIOS[1])
  })

  it('空列表显示空态', () => {
    render(<AudioTimeline audioList={[]} />)

    expect(screen.getByText('暂无音频时间轴数据')).toBeInTheDocument()
  })
})
