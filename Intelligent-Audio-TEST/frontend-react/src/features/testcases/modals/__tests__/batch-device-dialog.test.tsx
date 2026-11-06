/**
 * 批量设置逻辑音箱弹窗测试：
 * ① 选完逻辑音箱后触发器显示「[逻辑音箱] 名称」，而不是原始组 id（INT-1686 P2 同类问题）；
 * ② 提交载荷用 speakerGroupId（用例只关联逻辑音箱）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BatchDeviceDialog } from '@/features/testcases/modals/batch-device-dialog'
import { batchTestcaseAction } from '@/infrastructure/api/testcases-batch-api'

const batchActionMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: batchActionMock,
}))

vi.mock('@/application/devices/use-devices', () => ({
  usePlaybackSpeakerGroups: () => ({
    data: [
      {
        id: 8,
        name: '设备正左侧（1m-90°）',
        description: null,
        items: [{ id: 1, groupId: 8, labId: 38, playbackDeviceId: 12 }],
        createdAt: null,
        updatedAt: null,
      },
    ],
    isLoading: false,
  }),
}))

const GROUP_LABEL = '[逻辑音箱] 设备正左侧（1m-90°）'

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

beforeEach(() => {
  vi.clearAllMocks()
  batchActionMock.mockResolvedValue({ success: true })
})

describe('BatchDeviceDialog 逻辑音箱 Select（INT-1686 P2）', () => {
  it('选完逻辑音箱后触发器显示名称，不显示组 id', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: GROUP_LABEL }))

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('[逻辑音箱] 设备正左侧（1m-90°）')
    expect(trigger.textContent?.trim()).not.toBe('8')
  })

  it('提交载荷携带 speakerGroupId（不再提交实体设备）', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: GROUP_LABEL }))
    await user.click(screen.getByRole('button', { name: '确定' }))

    await waitFor(() => {
      expect(batchActionMock).toHaveBeenCalledWith(
        'update_playback_devices',
        ['tc-1', 'tc-2'],
        expect.objectContaining({
          playbackDevices: { speakerGroupId: 8 },
        })
      )
    })
  })
})
