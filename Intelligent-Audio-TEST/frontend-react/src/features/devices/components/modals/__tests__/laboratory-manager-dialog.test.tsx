/**
 * 实验室管理弹窗删除反馈测试（INT-1495 打回 P2-A）：
 * deleteLaboratory 走 deleteGuard，把 404 / 409 / 403 / 500 收敛成 { success:false, message }
 * 而不抛异常；弹窗必须按返回值分流——失败时提示后端文案、不提示「已删除」、不关闭确认框。
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Laboratory } from '@/domain/models/laboratory'

import { LaboratoryManagerDialog } from '../laboratory-manager-dialog'

const removeMock = vi.hoisted(() => vi.fn())

vi.mock('@/application/devices/use-devices', () => ({
  useLaboratoryMutations: () => ({
    create: { mutateAsync: vi.fn() },
    update: { mutateAsync: vi.fn() },
    remove: { mutateAsync: removeMock },
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const LAB: Laboratory = {
  id: 42,
  code: 'LAB-A-01',
  name: '声学实验室A',
  building: '研发中心东区',
  floor: '3 层',
  roomNumber: 'A301',
  description: null,
  status: 'active',
  deviceCount: 0,
  playbackDeviceCount: 0,
  testCaseCount: 0,
  createdAt: '2026-10-01T00:00:00Z',
  updatedAt: '2026-10-02T08:00:00Z',
}

async function openDeleteConfirm() {
  const user = userEvent.setup()
  render(<LaboratoryManagerDialog open onOpenChange={() => undefined} labs={[LAB]} />)
  await user.click(screen.getByRole('button', { name: `删除实验室 ${LAB.name}` }))
  const confirm = await screen.findByRole('alertdialog')
  await user.click(within(confirm).getByRole('button', { name: '删除' }))
  return confirm
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LaboratoryManagerDialog 删除反馈', () => {
  it('deleteGuard 返回 success:false 时提示后端文案，不提示已删除（打回 P2-A 假成功）', async () => {
    removeMock.mockResolvedValue({ success: false, message: '实验室下仍有设备，无法删除' })
    const confirm = await openDeleteConfirm()

    await waitFor(() => {
      expect(removeMock).toHaveBeenCalledWith(LAB.id)
      expect(toast.error).toHaveBeenCalledWith('实验室下仍有设备，无法删除')
    })
    expect(toast.success).not.toHaveBeenCalled()
    // 失败不关闭确认框，保留用户重试/取消的上下文
    expect(confirm).toBeInTheDocument()
  })

  it('失败且后端无文案时回落到通用提示', async () => {
    removeMock.mockResolvedValue({ success: false })
    await openDeleteConfirm()

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败，请重试')
    })
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('success:true 时才提示「实验室已删除」并关闭确认框', async () => {
    removeMock.mockResolvedValue({ success: true })
    await openDeleteConfirm()

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('实验室已删除')
    })
    expect(toast.error).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    })
  })
})
