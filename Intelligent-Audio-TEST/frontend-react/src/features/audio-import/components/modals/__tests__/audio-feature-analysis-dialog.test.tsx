/**
 * 音频特征分析·质量评估弹窗测试（INT-1663 §6.23）。
 * 口径：特征（频谱/能量/时域）+ 质量评估（SNR/动态范围/频率响应/评分）三态——
 * 加载中 Skeleton、失败错误态 + 重试（不得退化成空态）、正常值渲染；
 * 处理操作走 POST /audios/{id}/process（denoise/gain/trim），overwrite 破坏性二次确认。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AudioAsset } from '@/domain/models/audio'
import { AudioFeatureAnalysisDialog } from '@/features/audio-import/components/modals/audio-feature-analysis-dialog'

const getAudioFeaturesMock = vi.hoisted(() => vi.fn())
const getAudioQualityMock = vi.hoisted(() => vi.fn())
const processAudioMock = vi.hoisted(() => vi.fn())
const hasPermissionMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/audios-api', () => ({
  getAudioFeatures: getAudioFeaturesMock,
  getAudioQuality: getAudioQualityMock,
  processAudio: processAudioMock,
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({
    user: null,
    hasPermission: hasPermissionMock,
    hasAnyPermission: () => false,
  }),
}))

const AUDIO: AudioAsset = {
  id: 2071,
  name: '接线测试_特征分析.wav',
  originalFilename: '接线测试_特征分析.wav',
  filePath: 'D:/00_static/static/audios/接线测试_特征分析.wav',
  duration: 1.606,
  size: 308_390,
  sampleRate: 48_000,
  channels: 1,
  bitrate: 1_536_000,
  format: 'wav',
  audioType: 'dry',
  asrText: null,
  description: null,
  sourceLanguage: null,
  tags: [],
  annotations: [],
  createdAt: null,
  updatedAt: null,
}

/** 特征分析 200 响应（字段对照 audio_service compute_features 产出） */
const FEATURES = {
  spectral: {
    fundamentalRangeLow: 118.6,
    fundamentalRangeHigh: 402.31,
    dominantFrequency: 196,
    harmonicDistortion: 24.17,
  },
  energy: {
    averageEnergyDb: -22.4,
    peakEnergyDb: -1.2,
    energyConcentration: 0.8531,
  },
  timeDomain: {
    zeroCrossingRate: 0.0412,
    activeDurationRatio: 0.62,
    onsetTime: 0.128,
  },
  audioId: 2071,
  duration: 1.606,
}

/** 质量评估 200 响应（docker 15000 实测值） */
const QUALITY = {
  snrDb: 22.38,
  dynamicRangeDb: 40.7,
  frequencyResponseScore: 6.69,
  qualityScore: 30,
  audioId: 2071,
  duration: 1.606,
}

function renderDialog(audio: AudioAsset | null = AUDIO) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AudioFeatureAnalysisDialog open onOpenChange={() => undefined} audio={audio} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  hasPermissionMock.mockReturnValue(true)
  getAudioFeaturesMock.mockResolvedValue(FEATURES)
  getAudioQualityMock.mockResolvedValue(QUALITY)
  processAudioMock.mockResolvedValue({
    audioId: 2071,
    operation: 'denoise',
    mode: 'new',
    format: 'wav',
    filePath: 'oss://audios/processed/abc.wav',
    duration: 1.606,
    size: 154_188,
    newAudioId: 2549,
  })
})

describe('AudioFeatureAnalysisDialog 三态与真实值', () => {
  it('特征与质量评估正常返回 → 三区真实值渲染（无「待 FEAT」空态）', async () => {
    renderDialog()

    expect(await screen.findByText('196 Hz')).toBeInTheDocument()
    expect(screen.getByText('118.6–402.31 Hz')).toBeInTheDocument()
    expect(screen.getByText('24.17%')).toBeInTheDocument()
    expect(screen.getByText('-22.4 dBFS')).toBeInTheDocument()
    expect(screen.getByText('-1.2 dBFS')).toBeInTheDocument()
    expect(screen.getByText('0.8531')).toBeInTheDocument()
    expect(screen.getByText('0.0412')).toBeInTheDocument()
    expect(screen.getByText('0.62')).toBeInTheDocument()
    expect(screen.getByText('0.128 s')).toBeInTheDocument()
    expect(screen.getByText('22.38 dB')).toBeInTheDocument()
    expect(screen.getByText('40.7 dB')).toBeInTheDocument()
    expect(screen.getByText('6.69 分')).toBeInTheDocument()
    expect(screen.getByText('30 分')).toBeInTheDocument()

    expect(screen.queryByText('特征分析待后端接口')).not.toBeInTheDocument()
    expect(screen.queryByText(/待 FEAT/)).not.toBeInTheDocument()
  })

  it('特征分析失败 → 错误态 + 重试，不渲染空态；质量评估正常值不受影响', async () => {
    getAudioFeaturesMock.mockRejectedValue(new Error('特征分析失败: 服务不可用'))
    renderDialog()

    expect(await screen.findByText(/特征分析加载失败/)).toBeInTheDocument()
    expect(screen.getByText(/特征分析失败: 服务不可用/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
    // 质量评估独立成态：失败的分区不拖垮另一分区
    expect(await screen.findByText('22.38 dB')).toBeInTheDocument()
  })

  it('点击重试 → 重新请求特征分析并渲染真实值', async () => {
    getAudioFeaturesMock
      .mockRejectedValueOnce(new Error('特征分析失败: 服务不可用'))
      .mockResolvedValueOnce(FEATURES)
    renderDialog()

    const retry = await screen.findByRole('button', { name: '重试' })
    await userEvent.click(retry)

    expect(await screen.findByText('196 Hz')).toBeInTheDocument()
    expect(getAudioFeaturesMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByText(/特征分析加载失败/)).not.toBeInTheDocument()
  })

  it('默认降噪 + 生成新文件 → 提交 operation=denoise/mode=new', async () => {
    renderDialog()
    await screen.findByText('196 Hz')

    await userEvent.click(screen.getByRole('button', { name: '开始处理' }))

    await waitFor(() => expect(processAudioMock).toHaveBeenCalledTimes(1))
    expect(processAudioMock).toHaveBeenCalledWith(2071, {
      operation: 'denoise',
      mode: 'new',
    })
  })

  it('增益调整携带 gain_db；覆盖原文件须二次确认后才提交', async () => {
    renderDialog()
    await screen.findByText('196 Hz')

    await userEvent.click(screen.getByRole('button', { name: '增益调整' }))
    const gainInput = screen.getByLabelText('增益值（dB）')
    await userEvent.clear(gainInput)
    await userEvent.type(gainInput, '3.5')
    await userEvent.click(screen.getByRole('button', { name: '覆盖原文件' }))
    await userEvent.click(screen.getByRole('button', { name: '开始处理' }))

    // 破坏性操作先弹确认，未确认不落请求
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/原文件不可恢复/)).toBeInTheDocument()
    expect(processAudioMock).not.toHaveBeenCalled()

    await userEvent.click(within(dialog).getByRole('button', { name: '确定覆盖' }))

    await waitFor(() => expect(processAudioMock).toHaveBeenCalledTimes(1))
    expect(processAudioMock).toHaveBeenCalledWith(2071, {
      operation: 'gain',
      mode: 'overwrite',
      gainDb: 3.5,
    })
  })

  it('无 audio:update 权限 → 处理操作禁用并给出说明', async () => {
    hasPermissionMock.mockReturnValue(false)
    renderDialog()
    await screen.findByText('196 Hz')

    expect(screen.getByRole('button', { name: '降噪' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '开始处理' })).toBeDisabled()
    expect(
      screen.getByText(/当前账号无音频编辑权限（audio:update）/)
    ).toBeInTheDocument()
  })
})
