/**
 * 轮次「标签设备」面板目标播放设备 Select 闭合态测试（INT-1686 P2 追加项同根因）：
 * 选完设备后触发器显示设备名，而不是原始设备 id。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'
import { TagDevicePanel } from '@/features/testcases/modals/round-config/tag-device-panel'

const DEVICES: PlaybackDeviceOption[] = [
  { id: '8', name: '设备正左侧（1m-90°）', channel: 1, type: '干声' },
]

const DEVICE_LABEL = '设备正左侧（1m-90°） (通道 1) [干声]'

const setup = () =>
  render(
    <TagDevicePanel
      open
      onOpenChange={vi.fn()}
      tags={['行车噪声']}
      devices={DEVICES}
      onConfirm={vi.fn()}
    />
  )

describe('TagDevicePanel 目标播放设备 Select（INT-1686 P2）', () => {
  it('选完设备后触发器显示设备名，不显示设备 id', async () => {
    const user = userEvent.setup()
    setup()
    // 第一个 combobox 是标签，第二个是目标播放设备
    const [, deviceSelect] = screen.getAllByRole('combobox')
    await user.click(deviceSelect)
    await user.click(await screen.findByRole('option', { name: DEVICE_LABEL }))

    const trigger = screen.getAllByRole('combobox')[1]
    expect(trigger).toHaveTextContent('设备正左侧（1m-90°）')
    expect(trigger.textContent?.trim()).not.toBe('8')
  })
})
