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
}))

const DRAFT: RoundAudioDraft = {
  id: 'a1',
  audioId: 1,
  audioName: '接线测试音频.wav',
  spl: 65,
  deviceId: '8',
  deviceName: '设备正左侧（1m-90°）',
}

describe('AudioListStep 播放设备 Select（INT-1686 P2）', () => {
  it('已选设备时触发器显示设备名，不显示设备 id', () => {
    render(<AudioListStep value={[DRAFT]} onChange={vi.fn()} />)

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('设备正左侧（1m-90°）')
    expect(trigger).toHaveTextContent('(通道 1) [干声]')
    expect(trigger.textContent?.trim()).not.toBe('8')
  })
})
