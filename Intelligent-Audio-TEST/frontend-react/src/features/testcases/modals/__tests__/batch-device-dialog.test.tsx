/**
 * 批量设置播放设备弹窗 Select 闭合态显示测试（INT-1686 P2 追加项）：
 * 选完播放设备后触发器应显示「{设备名} (通道 {n}) [干声/噪声]」，而不是原始设备 id
 * （base-ui Select 未传 items 时闭合态回退 stringify 原始 value）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import { BatchDeviceDialog } from '@/features/testcases/modals/batch-device-dialog'
import { fetchRealPlaybackDevices } from '@/infrastructure/api/playback-api'

vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
}))

vi.mock('@/infrastructure/api/playback-api', () => ({
  fetchRealPlaybackDevices: vi.fn(),
  scanRealPlaybackDevices: vi.fn(),
}))

const DEVICE: PlaybackDevice = {
  id: 8,
  name: '设备正左侧（1m-90°）',
  model: null,
  description: null,
  deviceType: 'dry',
  sampleRate: null,
  channelIndex: 1,
  deviceUniqueId: null,
  status: 'online',
  currentSplMappingId: null,
  currentSplMappingName: null,
  labId: null,
  labName: null,
  occupied: false,
  supportedFormats: null,
  supportedChannels: null,
  createdAt: null,
  updatedAt: null,
}

vi.mocked(fetchRealPlaybackDevices).mockResolvedValue([DEVICE])

const DEVICE_LABEL = '设备正左侧（1m-90°） (通道 1) [干声]'

const setup = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <BatchDeviceDialog
        open
        onOpenChange={vi.fn()}
        count={2}
        ids={['tc-1', 'tc-2']}
        roundCount={1}
      />
    </QueryClientProvider>
  )
}

describe('BatchDeviceDialog 播放设备 Select（INT-1686 P2）', () => {
  it('选完设备后触发器显示设备名，不显示设备 id', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: DEVICE_LABEL }))

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('设备正左侧（1m-90°）')
    expect(trigger).toHaveTextContent('(通道 1) [干声]')
    expect(trigger.textContent?.trim()).not.toBe('8')
  })
})
