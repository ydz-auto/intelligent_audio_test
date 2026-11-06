/**
 * aiChatSessionStore URL 上下文名称解析（INT-1936）：
 * `/ai-chat?report={id}` / `?task={id}` 的上下文名称改由真实接口解析——
 * 命中显真实名称；404 / 接口失败降级为「报告 #id」/「任务 #id」并标 failed；
 * 任何情况下都不回落到 infrastructure/mock/ai-chat-mock 的演示名。
 */
import { waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/infrastructure/api/api-error'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'

const fetchReportDetailMock = vi.hoisted(() => vi.fn())
const fetchTaskDetailMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/reports-api', () => ({
  fetchReportDetail: fetchReportDetailMock,
}))

vi.mock('@/infrastructure/api/tasks-list-api', () => ({
  fetchTaskDetail: fetchTaskDetailMock,
}))

function resetStore(): void {
  useAiChatSession.setState({
    config: { providerId: undefined, modelId: undefined },
    messages: [],
    appliedContextKey: undefined,
    contextStatus: 'idle',
  })
  window.localStorage.clear()
}

describe('aiChatSessionStore URL 上下文（INT-1936 真实接口解析）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  it('报告 id 命中：先用降级名绑定，接口回来后换真实报告名与类型', async () => {
    fetchReportDetailMock.mockResolvedValue({
      id: 567,
      name: '对比报告_20261023211734',
      type: 'comparison',
    })

    useAiChatSession.getState().applyInitialContext({ report: '567' })

    // 同步阶段：id 已绑定、名称为编号占位，状态 loading（页面不闪空）
    expect(useAiChatSession.getState().config.reportContextId).toBe('567')
    expect(useAiChatSession.getState().config.reportContextLabel).toBe('报告 #567')
    expect(useAiChatSession.getState().contextStatus).toBe('loading')

    await waitFor(() => {
      expect(useAiChatSession.getState().contextStatus).toBe('resolved')
    })
    expect(fetchReportDetailMock).toHaveBeenCalledWith(567)
    expect(useAiChatSession.getState().config.reportContextLabel).toBe(
      '对比报告_20261023211734'
    )
    expect(useAiChatSession.getState().config.reportContextType).toBe('comparison')
  })

  it('任务 id 命中：走 GET /tasks/{id} 取任务名，类型固定 task_context', async () => {
    fetchTaskDetailMock.mockResolvedValue({ id: 658, name: '接线测试_INT1716_AUDIT_B' })

    useAiChatSession.getState().applyInitialContext({ task: '658' })

    expect(useAiChatSession.getState().config.reportContextLabel).toBe('任务 #658')
    await waitFor(() => {
      expect(useAiChatSession.getState().contextStatus).toBe('resolved')
    })
    expect(fetchTaskDetailMock).toHaveBeenCalledWith(658)
    expect(useAiChatSession.getState().config.reportContextLabel).toBe(
      '接线测试_INT1716_AUDIT_B'
    )
    expect(useAiChatSession.getState().config.reportContextType).toBe('task_context')
    expect(fetchReportDetailMock).not.toHaveBeenCalled()
  })

  it('报告 id 未命中（404）：保留「报告 #999999」并标 failed，无 mock 演示名', async () => {
    fetchReportDetailMock.mockRejectedValue(new ApiError({ httpStatus: 404 }))

    useAiChatSession.getState().applyInitialContext({ report: '999999' })

    await waitFor(() => {
      expect(useAiChatSession.getState().contextStatus).toBe('failed')
    })
    const { config } = useAiChatSession.getState()
    expect(config.reportContextId).toBe('999999')
    expect(config.reportContextLabel).toBe('报告 #999999')
    // 旧实现会从 MOCK_REPORTS 命中演示名（T320 等）；此处不得出现任何演示名
    expect(config.reportContextLabel).not.toContain('T320')
  })

  it('接口失败（网络 / 无权限）：同样降级编号名并标 failed，不清空上下文', async () => {
    fetchReportDetailMock.mockRejectedValue(new ApiError({ isNetworkError: true }))

    useAiChatSession.getState().applyInitialContext({ report: '567' })

    await waitFor(() => {
      expect(useAiChatSession.getState().contextStatus).toBe('failed')
    })
    const { config } = useAiChatSession.getState()
    expect(config.reportContextId).toBe('567')
    expect(config.reportContextLabel).toBe('报告 #567')
  })

  it('慢响应回来时上下文已切换：丢弃旧报告名，不覆盖当前会话', async () => {
    let resolveFirst: ((value: unknown) => void) | undefined
    fetchReportDetailMock
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve
          })
      )
      .mockResolvedValueOnce({ id: 568, name: '第二份报告', type: 'task' })

    useAiChatSession.getState().applyInitialContext({ report: '567' })
    useAiChatSession.getState().applyInitialContext({ report: '568' })

    await waitFor(() => {
      expect(useAiChatSession.getState().config.reportContextLabel).toBe('第二份报告')
    })

    resolveFirst?.({ id: 567, name: '第一份报告', type: 'task' })
    await Promise.resolve()

    expect(useAiChatSession.getState().config.reportContextId).toBe('568')
    expect(useAiChatSession.getState().config.reportContextLabel).toBe('第二份报告')
  })

  it('换上下文时保留用户已选的供应商 / 模型', async () => {
    fetchReportDetailMock.mockResolvedValue({ id: 567, name: '对比报告', type: 'comparison' })
    // 用户先在页面上选过供应商/模型（store 订阅即时落 localStorage）
    useAiChatSession.setState((state) => ({
      config: { ...state.config, providerId: 'p1', modelId: 'm1' },
    }))

    useAiChatSession.getState().applyInitialContext({ report: '567' })

    await waitFor(() => {
      expect(useAiChatSession.getState().contextStatus).toBe('resolved')
    })
    const { config } = useAiChatSession.getState()
    expect(config.providerId).toBe('p1')
    expect(config.modelId).toBe('m1')
    expect(config.reportContextId).toBe('567')
  })
})
