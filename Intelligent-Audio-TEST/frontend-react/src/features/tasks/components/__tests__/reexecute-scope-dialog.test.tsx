/**
 * 重新执行/重新评估范围弹窗回归测试。
 * 缺陷：提交成功后只 toast + 关弹窗，未失效 ['tasks'] 前缀 query，
 * 而日常列表 query 无轮询、全局 refetchOnWindowFocus=false，
 * 导致列表状态徽章停留在旧值，必须手动刷新页面才会变。
 * 本用例锁定「提交成功后失效任务列表 query」这一行为契约。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReexecuteScopeDialog } from '../reexecute-scope-dialog'

const retryTaskMock = vi.hoisted(() => vi.fn())
const reevaluateTaskMock = vi.hoisted(() => vi.fn())
const useTaskDetailMock = vi.hoisted(() => vi.fn())

vi.mock('@/application/tasks/use-task-detail', () => ({
  useTaskDetail: useTaskDetailMock,
}))

vi.mock('@/infrastructure/api/tasks-control-api', () => ({
  retryTask: retryTaskMock,
  reevaluateTask: reevaluateTaskMock,
}))

function renderDialog(actionType: 'retry' | 'reevaluate') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
  const onOpenChange = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <ReexecuteScopeDialog
        open
        onOpenChange={onOpenChange}
        taskId={417}
        taskName='任务A'
        actionType={actionType}
      />
    </QueryClientProvider>
  )
  return { invalidateSpy, onOpenChange }
}

describe('ReexecuteScopeDialog', () => {
  beforeEach(() => {
    retryTaskMock.mockReset()
    reevaluateTaskMock.mockReset()
    useTaskDetailMock.mockReset()
    useTaskDetailMock.mockReturnValue({
      data: { cases: [], reviewCount: 0 },
      isLoading: false,
      isError: false,
    })
    retryTaskMock.mockResolvedValue({})
    reevaluateTaskMock.mockResolvedValue({ message: '已发起重新评估' })
  })

  it('重新执行成功后失效任务列表 query 并关闭弹窗', async () => {
    const { invalidateSpy, onOpenChange } = renderDialog('retry')

    await userEvent.click(screen.getByRole('button', { name: '确认' }))

    await waitFor(() => {
      expect(retryTaskMock).toHaveBeenCalledTimes(1)
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['tasks'] })
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  it('重新评估成功后失效任务列表 query', async () => {
    const { invalidateSpy } = renderDialog('reevaluate')

    await userEvent.click(screen.getByRole('button', { name: '确认' }))

    await waitFor(() => {
      expect(reevaluateTaskMock).toHaveBeenCalledTimes(1)
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['tasks'] })
  })
})
