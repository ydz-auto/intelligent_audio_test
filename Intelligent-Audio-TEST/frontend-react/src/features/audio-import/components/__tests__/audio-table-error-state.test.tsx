/**
 * 音频表错误态测试（INT-1583）：列表接口失败不得伪装成「暂无音频文件」空态——
 * 首屏失败显示「音频列表加载失败」+ 重试；翻页/筛选失败但有旧数据时保留旧行 +
 * 行内提示；仅在无错误且无行时才渲染空态。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { AudioAsset } from '@/domain/models/audio'
import {
  AudioTable,
  type AudioTableProps,
} from '@/features/audio-import/components/audio-table'

const ROW: AudioAsset = {
  id: 101,
  name: '接线测试_音频A.wav',
  originalFilename: null,
  filePath: '/audios/101.wav',
  duration: 12,
  size: 1024,
  sampleRate: 16000,
  channels: 1,
  bitrate: 256000,
  format: 'WAV',
  audioType: 'dry',
  asrText: null,
  description: null,
  sourceLanguage: 'zh',
  tags: [],
  annotations: [],
  createdAt: '2026-10-20T08:00:00Z',
  updatedAt: '2026-10-20T08:00:00Z',
}

function baseProps(overrides: Partial<AudioTableProps> = {}): AudioTableProps {
  return {
    rows: [],
    loading: false,
    total: 0,
    searchKeyword: '',
    selectedIds: new Set<number>(),
    onToggleSelect: vi.fn(),
    onToggleSelectAll: vi.fn(),
    canUpdate: true,
    canConvert: true,
    canDelete: true,
    sortOrder: 'desc',
    onSortChange: vi.fn(),
    onEmptyUpload: vi.fn(),
    onPreview: vi.fn(),
    onMetadata: vi.fn(),
    onDownload: vi.fn(),
    onConvert: vi.fn(),
    onFeatureAnalysis: vi.fn(),
    onDelete: vi.fn(),
    ...overrides,
  }
}

describe('AudioTable 查询失败态（INT-1583）', () => {
  it('首屏失败：显示「音频列表加载失败」+ 重试，不渲染「暂无音频文件」空态', () => {
    const onRetry = vi.fn()
    render(<AudioTable {...baseProps({ isError: true, onRetry })} />)

    expect(screen.getByText('音频列表加载失败')).toBeInTheDocument()
    expect(screen.getByText('音频列表获取失败，请重试')).toBeInTheDocument()
    expect(screen.queryByText('暂无音频文件')).not.toBeInTheDocument()
    expect(screen.queryByText('点击「上传音频」导入首批音频，或调整筛选条件')).not.toBeInTheDocument()
  })

  it('首屏失败：点「重试」触发 refetch 回调', async () => {
    const onRetry = vi.fn()
    render(<AudioTable {...baseProps({ isError: true, onRetry })} />)

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('失败且有上次数据：保留旧行 + 行内提示 + 重试，不清空列表', async () => {
    const onRetry = vi.fn()
    render(
      <AudioTable
        {...baseProps({ rows: [ROW], total: 1, isError: true, onRetry })}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      '音频列表加载失败，当前显示的是上一次加载的数据'
    )
    expect(screen.getByText(ROW.name)).toBeInTheDocument()
    expect(screen.queryByText('暂无音频文件')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('无错误且无行：仍渲染「暂无音频文件」空态', () => {
    render(<AudioTable {...baseProps()} />)

    expect(screen.getByText('暂无音频文件')).toBeInTheDocument()
    expect(screen.queryByText('音频列表加载失败')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
