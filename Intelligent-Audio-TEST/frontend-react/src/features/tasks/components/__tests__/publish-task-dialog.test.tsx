/**
 * 发布任务弹窗组件测试（INT-1627）。
 * 覆盖：① 来源任务 Select 闭合态回显任务名（items 映射，不显示裸 id）；
 * ② 来源任务列表加载失败 → 错误态 + 重试，且预选任务不被锁死在 disabled；
 * ③ 点「重试」重新发起列表请求。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TaskListItem } from '@/domain/models/task'

import { PublishTaskDialog } from '../publish-task-dialog'

const fetchTaskListMock = vi.hoisted(() => vi.fn())
const publishTaskMock = vi.hoisted(() => vi.fn())
const hasPermissionMock = vi.hoisted(() => vi.fn(() => true))

vi.mock('@/infrastructure/api/tasks-list-api', () => ({
  fetchTaskList: fetchTaskListMock,
  publishTask: publishTaskMock,
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: hasPermissionMock }),
}))

const sourceTask = { id: 419, name: '小艺拒识E2E测试任务_2026/10/13 17:32:59' }

const listRow = {
  id: 419,
  name: sourceTask.name,
  execution_status: 'completed',
  total_cases: 12,
  device_count: 2,
} as unknown as TaskListItem

function renderDialog() {
  return render(
    <PublishTaskDialog open onOpenChange={vi.fn()} task={sourceTask} />
  )
}

describe('PublishTaskDialog', () => {
  beforeEach(() => {
    fetchTaskListMock.mockReset()
    publishTaskMock.mockReset()
    hasPermissionMock.mockReturnValue(true)
  })

  it('来源任务闭合态显示任务名而不是裸 id', async () => {
    fetchTaskListMock.mockResolvedValue({ items: [listRow], total: 1 })
    renderDialog()
    const trigger = screen.getByLabelText('选择来源任务')
    await waitFor(() => {
      expect(trigger).toHaveTextContent('小艺拒识E2E测试任务')
    })
    expect(trigger).not.toHaveTextContent(/^419$/)
  })

  it('列表加载失败：给出错误态与重试，预选来源任务仍可发布', async () => {
    fetchTaskListMock.mockRejectedValue(new Error('upstream timeout'))
    renderDialog()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('来源任务加载失败')
    })
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
    // 不把用户锁在 disabled：预选任务 id + 名称已具备 → 主钮可点
    expect(screen.getByRole('button', { name: '发布' })).not.toBeDisabled()
  })

  // INT-1627 返工回归：真实 HTTP 500 下 base-ui 会因选项映射坍缩（可用项从「加载中…」变空）
  // 对不在已渲染项里的受控值回调 onValueChange(null)。预选任务必须始终渲染成真实选项，
  // 否则触发器回退 placeholder、sourceTaskId 被清空 → 主钮 disabled（锁死用户）。
  it('列表失败时预选任务仍是真实选项，受控值不被清空', async () => {
    fetchTaskListMock.mockRejectedValue(new Error('HTTP 500'))
    renderDialog()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeTruthy()
    })

    // 受控值仍在：触发器回显任务名而非 placeholder / 裸 id
    const trigger = screen.getByLabelText('选择来源任务')
    expect(trigger).toHaveTextContent(sourceTask.name)
    expect(trigger).not.toHaveTextContent('选择要发布的任务')

    // 主钮可点（由后端 _get_publishable_task 兜底校验）
    expect(screen.getByRole('button', { name: '发布' })).not.toBeDisabled()

    // 展开下拉：预选任务渲染成真实选项（选项映射不坍缩为空）
    await userEvent.click(trigger)
    const optionTexts = await waitFor(() => {
      const texts = Array.from(
        document.querySelectorAll('[role="option"]')
      ).map((el) => (el.textContent ?? '').trim())
      expect(texts.length).toBeGreaterThan(0)
      return texts
    })
    expect(optionTexts.some((text) => text.includes(sourceTask.name))).toBe(true)
  })

  it('点「重试」重新发起来源任务列表请求', async () => {
    fetchTaskListMock.mockRejectedValue(new Error('upstream timeout'))
    renderDialog()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeTruthy()
    })

    fetchTaskListMock.mockResolvedValue({ items: [listRow], total: 1 })
    await userEvent.click(screen.getByRole('button', { name: '重试' }))

    await waitFor(() => {
      expect(fetchTaskListMock).toHaveBeenCalledTimes(2)
    })
    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull()
    })
  })
})
