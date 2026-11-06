/**
 * 参考参数步骤（11_用例域.md §5.1；INT-1642 接线）。
 * - 路径与内容来自 GET /testcases/{id}/rounds/{n}/ref-params（真实文件），不再硬编码；
 * - 编辑保存走 PUT 同端点，保存成功 toast「参考参数已保存」并回写缓存；
 * - 未生成（后端 404）/ 未关联音频 → 空态；非 404 失败 → 显式错误态 + 重试。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ApiError } from '@/infrastructure/api/api-error'
import {
  fetchRoundRefParams,
  updateRoundRefParams,
} from '@/infrastructure/api/testcases-api'
import { ReferenceStep } from '@/features/testcases/modals/round-config/reference-step'

vi.mock('@/infrastructure/api/testcases-api', () => ({
  fetchRoundRefParams: vi.fn(),
  updateRoundRefParams: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const mockedFetch = vi.mocked(fetchRoundRefParams)
const mockedUpdate = vi.mocked(updateRoundRefParams)

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, gcTime: 0 } },
})

const renderStep = (props: Partial<Parameters<typeof ReferenceStep>[0]> = {}) =>
  render(
    <QueryClientProvider client={queryClient}>
      <ReferenceStep caseId='tc-1' roundNumber={2} generated {...props} />
    </QueryClientProvider>
  )

const REF = {
  roundNumber: 2,
  referenceParamsPath: '/oss/ref_params/42/round_2/params.json',
  referenceParams: { asr_reference_text: '你好世界' },
}

describe('ReferenceStep 参考参数（INT-1642）', () => {
  beforeEach(() => {
    queryClient.clear()
  })

  it('展示后端返回的真实路径，不再硬编码 tc-001 路径', async () => {
    mockedFetch.mockResolvedValue(REF)
    renderStep()
    expect(await screen.findByText(REF.referenceParamsPath)).toBeInTheDocument()
    expect(screen.queryByText(/tc-001/)).not.toBeInTheDocument()
    expect(mockedFetch).toHaveBeenCalledWith('tc-1', 2)
  })

  it('编辑保存：PUT 解析后的 JSON，成功 toast「参考参数已保存」', async () => {
    const user = userEvent.setup()
    mockedFetch.mockResolvedValue(REF)
    mockedUpdate.mockResolvedValue({
      ...REF,
      referenceParams: { asr_reference_text: '新的参考文本' },
    })
    renderStep()

    await user.click(await screen.findByRole('button', { name: /查看\/编辑/ }))
    const textarea = await screen.findByPlaceholderText('编辑参考参数 JSON…')
    expect((textarea as HTMLTextAreaElement).value).toContain('你好世界')

    fireEvent.change(textarea, {
      target: { value: '{"asr_reference_text":"新的参考文本"}' },
    })
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalledTimes(1))
    expect(mockedUpdate).toHaveBeenCalledWith('tc-1', 2, {
      asr_reference_text: '新的参考文本',
    })
    expect(toast.success).toHaveBeenCalledWith('参考参数已保存')
  })

  it('非法 JSON：不发请求，toast 保存失败', async () => {
    const user = userEvent.setup()
    mockedFetch.mockResolvedValue(REF)
    renderStep()

    await user.click(await screen.findByRole('button', { name: /查看\/编辑/ }))
    const textarea = await screen.findByPlaceholderText('编辑参考参数 JSON…')
    fireEvent.change(textarea, { target: { value: 'not json' } })
    await user.click(screen.getByRole('button', { name: /保存/ }))

    expect(mockedUpdate).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining('参考参数保存失败')
    )
  })

  it('后端 404（未生成）→ 空态文案，不报错', async () => {
    mockedFetch.mockRejectedValue(
      new ApiError({ code: 404, httpStatus: 400, message: '第 2 轮未配置参考参数路径' })
    )
    renderStep()
    expect(
      await screen.findByText(/参考参数将在音频关联后自动生成/)
    ).toBeInTheDocument()
  })

  it('未关联音频（generated=false）→ 空态且不请求', () => {
    renderStep({ generated: false })
    expect(
      screen.getByText(/参考参数将在音频关联后自动生成/)
    ).toBeInTheDocument()
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  it('后端 404 但用例独立列有该轮路径 → 展示真实路径 + 内容读取失败（不伪装未生成）', async () => {
    mockedFetch.mockRejectedValue(
      new ApiError({ code: 404, httpStatus: 400, message: '未找到第 2 轮' })
    )
    renderStep({ pathFallback: '/oss/ref_params/tc-1/round_2.json' })
    expect(
      await screen.findByText(/参考参数内容读取失败/)
    ).toBeInTheDocument()
    expect(
      screen.getByText('/oss/ref_params/tc-1/round_2.json')
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/参考参数将在音频关联后自动生成/)
    ).not.toBeInTheDocument()
  })

  it('非 404 失败 → 显式错误态 + 重试', async () => {
    mockedFetch.mockRejectedValue(
      new ApiError({ httpStatus: 500, message: '获取参考参数失败' })
    )
    renderStep()
    expect(
      await screen.findByText(/参考参数加载失败：获取参考参数失败/)
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument()
  })
})
