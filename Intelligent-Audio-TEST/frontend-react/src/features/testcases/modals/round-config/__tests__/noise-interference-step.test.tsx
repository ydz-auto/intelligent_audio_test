/**
 * 噪声与干扰步骤（11_用例域.md §5.1；INT-1642 P3-3）。
 * 导入未匹配警示条改数据驱动：仅当干扰音频以文件名回填（audio_id 缺失）时显示，
 * 不再常驻「演示提示条」字样。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { RoundNoiseDraft } from '@/domain/models/testCaseRound'
import { NoiseInterferenceStep } from '@/features/testcases/modals/round-config/noise-interference-step'

vi.mock('@/infrastructure/api/playback-api', () => ({
  fetchRealPlaybackDevices: vi.fn().mockResolvedValue([]),
}))

// 音频选择子弹窗（关闭态）依赖音频库 API，测试里给空实现
vi.mock('@/infrastructure/api/audios-api', () => ({
  fetchAudioTags: vi.fn().mockResolvedValue([]),
  fetchAudios: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchFolderTree: vi.fn().mockResolvedValue([]),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const noise = (audioId: number | string, audioName?: string): RoundNoiseDraft => ({
  backgroundNoise: null,
  voiceprint: {
    enabled: false,
    audioId: null,
    audioName: null,
    playbackDeviceId: null,
    spl: 75,
    waitSec: 5,
  },
  interferers: [
    {
      id: 'ifr-1',
      audioId,
      audioName: audioName ?? null,
      playbackDeviceId: null,
      spl: 70,
      startDelay: 0,
      loop: false,
    },
  ],
})

const renderStep = (value: RoundNoiseDraft) =>
  render(
    <QueryClientProvider client={queryClient}>
      <NoiseInterferenceStep value={value} onChange={vi.fn()} />
    </QueryClientProvider>
  )

describe('NoiseInterferenceStep 导入未匹配警示条（INT-1642）', () => {
  it('文件名回填的干扰音频 → 显示真实文件名提示，且不再出现「演示提示条」', () => {
    renderStep(noise('noise_a.wav', 'noise_a.wav'))
    expect(screen.getByText(/导入时未匹配到音频 ID 的干扰音频/)).toBeInTheDocument()
    // 文件名在提示条与音频卡各出现一次
    expect(screen.getAllByText(/noise_a\.wav/).length).toBeGreaterThan(0)
    expect(screen.getByText(/保存后后端会按文件名解析/)).toBeInTheDocument()
    expect(screen.queryByText(/演示提示条/)).not.toBeInTheDocument()
  })

  it('真实音频 id（数字）→ 不显示提示条', () => {
    renderStep(noise(123, '真实噪声音频'))
    expect(
      screen.queryByText(/导入时未匹配到音频 ID/)
    ).not.toBeInTheDocument()
  })
})
