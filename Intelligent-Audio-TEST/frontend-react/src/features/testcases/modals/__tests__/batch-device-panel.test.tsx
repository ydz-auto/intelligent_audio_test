/**
 * 轮次「批量设置逻辑音箱」面板 Select 闭合态测试（INT-1686 P2 追加项同根因）：
 * 选完逻辑音箱后触发器显示名称，而不是原始组 id。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { PlaybackDeviceOption } from '@/features/testcases/modals/round-config/audio-list-types'
import { BatchDevicePanel } from '@/features/testcases/modals/round-config/batch-device-panel'

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
    <BatchDevicePanel
      open
      onOpenChange={vi.fn()}
      devices={DEVICES}
      selectedCount={2}
      onConfirm={vi.fn()}
    />
  )

describe('BatchDevicePanel 逻辑音箱 Select（INT-1686 P2）', () => {
  it('选完逻辑音箱后触发器显示名称，不显示组 id', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: DEVICE_LABEL }))

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('设备正左侧（1m-90°）')
    expect(trigger.textContent?.trim()).not.toBe('8')
  })
})
