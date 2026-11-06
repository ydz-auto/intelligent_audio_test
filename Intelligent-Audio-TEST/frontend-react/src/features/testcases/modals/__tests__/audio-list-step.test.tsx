/**
 * 轮次步骤②「音频列表」播放设备 Select 闭合态测试（INT-1686 P2 追加项同根因）：
 * 已选设备回填时触发器显示设备名，而不是原始设备 id。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { RoundAudioDraft } from '@/domain/models/testCaseRound'
import { AudioListStep } from '@/features/testcases/modals/round-config/audio-list-step'

vi.mock('@/application/devices/use-devices', () => ({
  usePlaybackDevices: () => ({
    data: [{ id: 8, name: '设备正左侧（1m-90°）', channelIndex: 1, deviceType: 'dry' }],
    isLoading: false,
  }),
  usePlaybackSpeakerGroups: () => ({
    data: [
      {
        id: 7,
        name: '设备正面（0.5m+0°）',
        description: null,
        items: [{ id: 1, groupId: 7, labId: 38, playbackDeviceId: 5 }],
        createdAt: null,
        updatedAt: null,
      },
    ],
    isLoading: false,
  }),
  useLaboratories: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/infrastructure/api/audioLibraryApi', () => ({
  fetchAudioLibrary: () =>
    Promise.resolve({
      items: [],
      total: 0,
      pages: 0,
      stats: { totalFiles: 0, totalSize: '', totalDuration: '', todayUploads: 0 },
    }),
}))

// INT-1734 合入 INT-1614 后，音频选择窗内的上传窗改走 useUploadRoundScope → useEvaluationDimensions
// （useQuery 需 QueryClientProvider）。本文件只断言 Select 闭合态文案，维度目录桩成空即可。
vi.mock('@/application/evaluation/use-dimensions', () => ({
  useEvaluationDimensions: () => ({ data: [], isLoading: false }),
  useAlgorithmDimensions: () => ({ data: [], isLoading: false }),
}))

const DRAFT: RoundAudioDraft = {
  id: 'a1',
  audioId: 1,
  audioName: '接线测试音频.wav',
  spl: 65,
  deviceId: '',
  deviceName: null,
  speakerGroupId: '7',
  speakerGroupName: '设备正面（0.5m+0°）',
}

describe('AudioListStep 逻辑音箱 Select（用例只关联逻辑音箱）', () => {
  it('已关联逻辑音箱时触发器显示逻辑音箱名，不显示组 id', () => {
    render(<AudioListStep value={[DRAFT]} onChange={vi.fn()} />)

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('[逻辑音箱] 设备正面（0.5m+0°）')
    expect(trigger.textContent?.trim()).not.toBe('7')
  })

  it('卡片底部给出按实验室换绑的说明', () => {
    render(<AudioListStep value={[DRAFT]} onChange={vi.fn()} />)

    expect(screen.getByText(/执行时按实验室自动换成本实验室的实体音箱/)).toBeInTheDocument()
  })

  it('未关联逻辑音箱时触发器显示占位文案', () => {
    render(
      <AudioListStep
        value={[{ ...DRAFT, speakerGroupId: '', speakerGroupName: null }]}
        onChange={vi.fn()}
      />
    )

    expect(screen.getByRole('combobox')).toHaveTextContent('请选择逻辑音箱')
  })
})
