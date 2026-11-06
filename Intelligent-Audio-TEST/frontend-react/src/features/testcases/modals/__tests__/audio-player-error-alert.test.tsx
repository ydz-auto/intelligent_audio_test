/**
 * 试听播放器错误条（INT-1673 P3-1）：
 * Alert destructive 的关闭钮按组件约定包成动作位（data-slot='alert-action'，触发 Alert
 * 的 pr-18 预留位）并绝对定位到右上角，不再落到 grid 第 2 行把错误条撑高、整行可点。
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AudioPlayerPanel } from '@/features/testcases/modals/audio-player-dialog'

const streamMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/audios-api', () => ({
  stream: streamMock,
  preview: vi.fn(),
  stopPreview: vi.fn(),
  fetchAudioDuration: () => Promise.resolve(null),
}))

vi.mock('@/application/devices/use-devices', () => ({
  usePlaybackDevices: () => ({ data: [], isLoading: false }),
}))

describe('试听播放器错误条关闭钮（INT-1673 P3-1）', () => {
  beforeEach(() => {
    streamMock.mockReset()
    streamMock.mockRejectedValue(new Error('stream failed'))
  })

  it('关闭钮是 Alert 动作位（data-slot=alert-action）且固定右上角', async () => {
    render(
      <AudioPlayerPanel
        mode='frontend'
        onBack={vi.fn()}
        audioId={42}
        audioName='sample.wav'
      />
    )
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('获取音频流失败')).toBeInTheDocument()

    const close = within(alert).getByRole('button', { name: '关闭错误提示' })
    // Alert 用 has-data-[slot=alert-action] 预留右侧内边距并置 relative，动作钮须带该 slot
    expect(close).toHaveAttribute('data-slot', 'alert-action')
    expect(close.className).toContain('absolute')
    expect(close.className).toContain('top-2')
    expect(close.className).toContain('right-2')
  })

  it('点关闭钮清除错误条', async () => {
    const user = userEvent.setup()
    render(
      <AudioPlayerPanel
        mode='frontend'
        onBack={vi.fn()}
        audioId={42}
        audioName='sample.wav'
      />
    )
    const alert = await screen.findByRole('alert')
    await user.click(within(alert).getByRole('button', { name: '关闭错误提示' }))
    await waitFor(() =>
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    )
  })
})
