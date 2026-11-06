/**
 * 轮次「标签逻辑音箱」面板目标 Select 闭合态测试（INT-1686 P2 追加项同根因）：
 * 选完逻辑音箱后触发器显示名称，而不是原始组 id。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'
import { TagDevicePanel } from '@/features/testcases/modals/round-config/tag-device-panel'

const DEVICES: PlaybackDeviceOption[] = [
  {
    id: '8',
    name: '设备正左侧（1m-90°）',
    label: '[逻辑音箱] 设备正左侧（1m-90°）',
  },
]

const DEVICE_LABEL = '[逻辑音箱] 设备正左侧（1m-90°）'

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

describe('TagDevicePanel 目标逻辑音箱 Select（INT-1686 P2）', () => {
  it('选完逻辑音箱后触发器显示名称，不显示组 id', async () => {
    const user = userEvent.setup()
    setup()
    // 第一个 combobox 是标签，第二个是目标逻辑音箱
    const [, deviceSelect] = screen.getAllByRole('combobox')
    await user.click(deviceSelect)
    await user.click(await screen.findByRole('option', { name: DEVICE_LABEL }))

    const trigger = screen.getAllByRole('combobox')[1]
    expect(trigger).toHaveTextContent('设备正左侧（1m-90°）')
    expect(trigger.textContent?.trim()).not.toBe('8')
  })
})
