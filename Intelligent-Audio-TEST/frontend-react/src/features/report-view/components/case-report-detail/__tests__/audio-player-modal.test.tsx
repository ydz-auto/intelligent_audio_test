/**
 * 试听弹窗总时长口径（INT-1860）：有真实流时只认媒体元数据，元数据未到 / 流不可用显示「—」，
 * 不再回落到 audio_id 派生演示时长（404 时仍显示 0:36 的假时长）；无真实流（mock 播放）保留派生时长。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AudioPlayerModal, type AudioItemMeta } from '../audio-player-modal'

vi.mock('@/infrastructure/api/audios-api', () => ({
  stream: vi.fn(async () => 'https://rustfs.local/iat/case_pcm/402/user_wav.wav?sign=x'),
}))

const PRESIGNED_URL = 'https://rustfs.local/iat/case_pcm/402/user_wav.wav?sign=x'

const realStreamAudio: AudioItemMeta = {
  audio_id: 'user_wav',
  audio_name: 'user_wav',
  audio_type: 'result',
  url: PRESIGNED_URL,
}

function durationText(): string {
  return screen.getByTestId('audio-duration').textContent ?? ''
}

/** Dialog 内容经 base-ui Portal 挂到 document.body，不在 render 的 container 里 */
function audioElement(): HTMLAudioElement {
  const el = document.querySelector('audio')
  if (!el) throw new Error('未渲染 <audio> 元素')
  return el
}

/**
 * 按真实使用路径打开（先挂载关闭态再切 open）：Dialog 首次挂载即 open 时内容要到
 * mount effect 之后才出现，`<audio>` 的 ref/事件监听会错过该 commit；用户点开弹窗时
 * 组件早已挂载，走的正是「关闭 → 打开」这条路径。
 */
function renderOpened(audio: AudioItemMeta) {
  const view = render(<AudioPlayerModal open={false} onOpenChange={() => {}} audio={audio} />)
  view.rerender(<AudioPlayerModal open onOpenChange={() => {}} audio={audio} />)
  return view
}

describe('AudioPlayerModal 总时长（INT-1860）', () => {
  it('真实流不可用（未拿到元数据 / error）时总时长显示「—」，不显示派生时长', async () => {
    renderOpened(realStreamAudio)

    // 派生时长对 user_wav 是 0:36，修复前这里会显示该假值
    expect(durationText()).toBe('—')
    expect(screen.queryByText('0:36')).toBeNull()

    fireEvent.error(audioElement())

    expect(await screen.findByText('音频播放失败，请检查音频文件是否有效')).toBeTruthy()
    expect(durationText()).toBe('—')
    expect(screen.queryByText('0:36')).toBeNull()
  })

  it('真实流 loadedmetadata 到达后显示媒体真实时长', async () => {
    renderOpened(realStreamAudio)
    const el = audioElement()
    // jsdom 的 HTMLMediaElement 不加载媒体，直接注入元数据时长再触发事件
    Object.defineProperty(el, 'duration', { configurable: true, value: 87.6 })
    fireEvent(el, new Event('loadedmetadata'))

    await waitFor(() => expect(durationText()).toBe('1:27'))
  })

  it('无真实流（mock 播放）仍按 audio_id 派生演示时长，时长位不出现「—」', () => {
    renderOpened({ audio_id: 'user_wav', audio_name: 'user_wav', audio_type: 'result' })

    expect(durationText()).toBe('0:36')
  })
})
