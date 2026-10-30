/**
 * 逻辑音箱管理弹窗测试：
 * ① 组列表与「已绑定实验室」数量展示（空态文案）；
 * ② 新建逻辑音箱调用 create（名称/描述入参）并提示成功；
 * ③ 删除走 deleteGuard 返回值分流——success:false 时提示后端文案、不提示已删除。
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PlaybackSpeakerGroup } from '@/domain/models/playbackSpeakerGroup'

import { PlaybackSpeakerGroupDialog } from '../playback-speaker-group-dialog'

const createMock = vi.hoisted(() => vi.fn())
const removeMock = vi.hoisted(() => vi.fn())
const setItemMock = vi.hoisted(() => vi.fn())
const removeItemMock = vi.hoisted(() => vi.fn())
const groupsData = vi.hoisted(() => ({ value: [] as PlaybackSpeakerGroup[] }))

vi.mock('@/application/devices/use-devices', () => ({
  usePlaybackSpeakerGroups: () => ({ data: groupsData.value, isLoading: false }),
  useLaboratories: () => ({ data: [] }),
  usePlaybackDevices: () => ({ data: [] }),
  usePlaybackSpeakerGroupMutations: () => ({
    create: { mutateAsync: createMock },
    update: { mutateAsync: vi.fn() },
    remove: { mutateAsync: removeMock },
    setItem: { mutateAsync: setItemMock },
    removeItem: { mutateAsync: removeItemMock },
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

const GROUP: PlaybackSpeakerGroup = {
  id: 7,
  name: '设备正面（0.5m+0°）',
  description: '验证用',
  items: [
    { id: 1, groupId: 7, labId: 38, playbackDeviceId: 5 },
    { id: 2, groupId: 7, labId: 40, playbackDeviceId: 83 },
  ],
  createdAt: '2026-10-30T02:00:00Z',
  updatedAt: '2026-10-30T03:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  groupsData.value = [GROUP]
})

describe('PlaybackSpeakerGroupDialog', () => {
  it('展示逻辑音箱列表与已绑定实验室数量', () => {
    render(<PlaybackSpeakerGroupDialog open onOpenChange={() => undefined} />)

    expect(screen.getByText(GROUP.name)).toBeInTheDocument()
    expect(screen.getByText('已绑定实验室')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('组为空时给出空态文案', () => {
    groupsData.value = []
    render(<PlaybackSpeakerGroupDialog open onOpenChange={() => undefined} />)

    expect(screen.getByText('暂无逻辑音箱')).toBeInTheDocument()
  })

  it('新建逻辑音箱：名称为空提示错误且不提交', async () => {
    const user = userEvent.setup()
    render(<PlaybackSpeakerGroupDialog open onOpenChange={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '新建逻辑音箱' }))

    expect(toast.error).toHaveBeenCalledWith('请填写逻辑音箱名称')
    expect(createMock).not.toHaveBeenCalled()
  })

  it('新建逻辑音箱：提交名称与描述并提示成功', async () => {
    createMock.mockResolvedValue({ success: true, id: 8 })
    const user = userEvent.setup()
    render(<PlaybackSpeakerGroupDialog open onOpenChange={() => undefined} />)

    await user.type(screen.getByLabelText('名称'), '设备背面（0.5m+180°）')
    await user.type(screen.getByLabelText('描述'), '后排位置')
    await user.click(screen.getByRole('button', { name: '新建逻辑音箱' }))

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith({
        name: '设备背面（0.5m+180°）',
        description: '后排位置',
      })
      expect(toast.success).toHaveBeenCalledWith('逻辑音箱已创建')
    })
  })

  it('删除失败时提示后端文案，不提示已删除', async () => {
    removeMock.mockResolvedValue({ success: false, message: '逻辑音箱已被用例关联，无法删除' })
    const user = userEvent.setup()
    render(<PlaybackSpeakerGroupDialog open onOpenChange={() => undefined} />)

    await user.click(screen.getByRole('button', { name: `删除逻辑音箱 ${GROUP.name}` }))
    const confirm = await screen.findByRole('alertdialog')
    await user.click(within(confirm).getByRole('button', { name: '删除' }))

    await waitFor(() => {
      expect(removeMock).toHaveBeenCalledWith(GROUP.id)
      expect(toast.error).toHaveBeenCalledWith('逻辑音箱已被用例关联，无法删除')
    })
    expect(toast.success).not.toHaveBeenCalled()
  })
})
