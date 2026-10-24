/**
 * 轮次「批量设置播放设备」面板 Select 闭合态测试（INT-1686 P2 追加项同根因）：
 * 选完设备后触发器显示设备名，而不是原始设备 id。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'
import { BatchDevicePanel } from '@/features/testcases/modals/round-config/batch-device-panel'

const DEVICES: PlaybackDeviceOption[] = [
  { id: '8', name: '设备正左侧（1m-90°）', channel: 1, type: '干声' },
]

const DEVICE_LABEL = '设备正左侧（1m-90°） (通道 1) [干声]'

const setup = () =>
  render(
    <BatchDevicePanel
      open
      onOpenChange={vi.fn()}
      devices={DEVICES}
      selectedCount={2}
      onConfirm={vi.fn()}
    />
  )

describe('BatchDevicePanel 播放设备 Select（INT-1686 P2）', () => {
  it('选完设备后触发器显示设备名，不显示设备 id', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: DEVICE_LABEL }))

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('设备正左侧（1m-90°）')
    expect(trigger.textContent?.trim()).not.toBe('8')
  })
})
