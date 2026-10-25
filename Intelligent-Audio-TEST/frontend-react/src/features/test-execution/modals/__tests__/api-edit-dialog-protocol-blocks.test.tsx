/**
 * A3（INT-1791）：请求模板页签内的协议区块（HTTP / WS / gRPC / SSE）显隐与校验。
 * 覆盖走查表 #1（区块随协议切换）、#2（切协议已填值不丢）、#5（非法配置被拦截）、
 * SSE 不显示 body_template、以及「切回原协议草稿仍在」。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiConfig } from '@/domain/models/apiConfig'

const { saveMock, fetchApiMock, uploadProtoMock } = vi.hoisted(() => ({
  saveMock: vi.fn(async (_input: Record<string, unknown>) => undefined),
  fetchApiMock: vi.fn(async (_id: number): Promise<unknown> => null),
  uploadProtoMock: vi.fn(async () => {
    throw new Error('Failed to fetch 404: 协议文件上传接口尚未上线')
  }),
}))

vi.mock('@/application/test-execution/useApisCrud', () => ({
  useApisCrud: () => ({ save: saveMock }),
}))

vi.mock('@/infrastructure/api/test-execution-api', () => ({
  fetchApi: fetchApiMock,
  uploadApiProto: uploadProtoMock,
  parseApiResponsePreview: vi.fn(),
}))

vi.mock('@/application/test-execution/useTestAlgorithmOptions', () => ({
  useTestAlgorithmOptions: () => ({ data: [{ id: 'voice_llm', name: '小艺语音大模型' }] }),
}))

import { ApiEditDialog } from '../api-edit-dialog'

const BASE_API: ApiConfig = {
  id: 21,
  name: '接线测试_INT1791',
  vendor: null,
  description: null,
  status: 'online',
  algorithmType: 'voice_llm',
  defaultMaxProcess: 5,
  defaultMaxTimeout: 30,
  defaultMaxAudioDuration: 60,
  healthScore: 100,
  endpoints: [],
  maxConcurrent: 5,
  protocol: 'http',
  streaming: false,
  meta: {},
  audioConfig: null,
}

function renderDialog(api: ApiConfig) {
  fetchApiMock.mockResolvedValue(null)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ApiEditDialog open onOpenChange={vi.fn()} api={api} />
    </QueryClientProvider>
  )
}

function openRequestTab() {
  fireEvent.click(screen.getByRole('tab', { name: '请求模板' }))
}

beforeEach(() => {
  saveMock.mockClear()
  fetchApiMock.mockClear()
  uploadProtoMock.mockClear()
})

describe('A3 协议区块显隐（request 页签内，不新增页签）', () => {
  it('页签骨架不随协议变化：仍是五页签', () => {
    renderDialog({ ...BASE_API, protocol: 'grpc', streaming: true })
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      '基础',
      '请求模板',
      '响应解析',
      '输出字段',
      '映射',
    ])
  })

  it('HTTP 组：方法 / 请求头 / 请求体模板，无 gRPC / SSE 控件', () => {
    renderDialog(BASE_API)
    openRequestTab()
    expect(screen.getByLabelText('请求体模板（body_template）')).toBeInTheDocument()
    expect(screen.queryByLabelText('proto_object_key')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('事件名字段（event_name_field）')).not.toBeInTheDocument()
  })

  it('gRPC 组：proto 三元组 / service / method / method_kind / metadata / deadline；无 body_template', () => {
    renderDialog({ ...BASE_API, protocol: 'grpc', streaming: false })
    openRequestTab()
    expect(screen.getByLabelText('proto_object_key')).toBeInTheDocument()
    expect(screen.getByLabelText('service')).toBeInTheDocument()
    expect(screen.getByLabelText('method')).toBeInTheDocument()
    expect(screen.getByLabelText('method_kind')).toBeInTheDocument()
    expect(screen.getByText('未配置 metadata')).toBeInTheDocument()
    expect(screen.getByLabelText('deadline_ms（毫秒）')).toBeInTheDocument()
    expect(screen.queryByLabelText('请求体模板（body_template）')).not.toBeInTheDocument()
    expect(screen.queryByText('SSE 请求参数（params）')).not.toBeInTheDocument()
  })

  it('SSE 组：method / headers + SSE 七键；**不显示 body_template**', () => {
    renderDialog({ ...BASE_API, protocol: 'sse', streaming: true })
    openRequestTab()
    expect(screen.getByLabelText('SSE 请求方法')).toBeInTheDocument()
    expect(screen.getByLabelText('事件名字段（event_name_field）')).toBeInTheDocument()
    expect(screen.getByText('未配置请求参数')).toBeInTheDocument()
    expect(screen.getByLabelText('SSE 重连开关')).toBeInTheDocument()
    expect(screen.getByLabelText('重连次数上限（max_reconnect_attempts）')).toBeInTheDocument()
    expect(screen.getByLabelText('重连退避上限（retry_ms）')).toBeInTheDocument()
    expect(screen.getByLabelText('空闲超时（idle_timeout_ms）')).toBeInTheDocument()
    expect(screen.getByLabelText('整体时长上限（max_duration_ms）')).toBeInTheDocument()
    // A2 执行侧在 SSE 下从不读 meta.body_template → 不给死控件
    expect(screen.queryByLabelText('请求体模板（body_template）')).not.toBeInTheDocument()
    expect(screen.getByText(/句子结束 \/ 会话结束标记在「响应解析」页签/)).toBeInTheDocument()
    // SSE 不显示会话配置 / 节奏控制（那是 WS / HTTP 流式的键）
    expect(screen.queryByLabelText('会话配置（session_config）')).not.toBeInTheDocument()
  })

  it('SSE 组只读提示指回响应解析页签，且不自带句子结束标记控件', () => {
    renderDialog({ ...BASE_API, protocol: 'sse', streaming: true })
    openRequestTab()
    expect(screen.queryByText(/句结束标志（sentence_end_mapping）/)).not.toBeInTheDocument()
  })
})

describe('A3 切协议不丢值', () => {
  it('HTTP 填了方法 → 切 gRPC → 切回 HTTP，值仍在', async () => {
    const user = userEvent.setup()
    renderDialog(BASE_API)
    openRequestTab()

    const bodyInput = screen.getByLabelText('请求体模板（body_template）')
    fireEvent.change(bodyInput, { target: { value: '{"text":"{{text}}"}' } })

    // 协议下拉在基础页签；切到基础再改协议（真实用户路径）
    fireEvent.click(screen.getByRole('tab', { name: '基础' }))
    await user.click(screen.getByRole('combobox', { name: '协议' }))
    await user.click(await screen.findByRole('option', { name: /gRPC/ }))
    fireEvent.click(screen.getByRole('tab', { name: '请求模板' }))
    await waitFor(() => expect(screen.getByLabelText('proto_object_key')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('tab', { name: '基础' }))
    await user.click(screen.getByRole('combobox', { name: '协议' }))
    await user.click(await screen.findByRole('option', { name: /HTTP/ }))
    fireEvent.click(screen.getByRole('tab', { name: '请求模板' }))
    await waitFor(() =>
      expect(screen.getByLabelText('请求体模板（body_template）')).toHaveValue(
        '{"text":"{{text}}"}'
      )
    )
  })
})

describe('A3 非法配置拦截保存', () => {
  it('gRPC 必填缺失 → 保存被拦、请求不发出、控件上报错', async () => {
    renderDialog({ ...BASE_API, protocol: 'grpc', streaming: false })
    openRequestTab()
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() =>
      expect(
        screen.getByText('缺少 proto 文件引用（proto_object_key）：上传 .proto 后自动填入')
      ).toBeInTheDocument()
    )
    expect(screen.getByText('请填写或选择 service')).toBeInTheDocument()
    expect(screen.getByText('请填写或选择 method')).toBeInTheDocument()
    expect(screen.getByText('请选择 method_kind')).toBeInTheDocument()
    expect(saveMock).not.toHaveBeenCalled()
  })

  it('SSE retry_ms 越界 → 保存被拦并定位控件', async () => {
    renderDialog({ ...BASE_API, protocol: 'sse', streaming: true })
    openRequestTab()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('重连退避上限（retry_ms）'), '60001')
    expect(screen.getByLabelText('重连退避上限（retry_ms）')).toHaveValue(60001)
    // jsdom 在数字输入获得焦点后不再执行 button 的隐式提交（base-ui Dialog 焦点处理叠加），
    // 这里直接派发 form submit —— 走的是与点「保存」完全相同的 RHF handleSubmit 路径。
    fireEvent.submit(document.querySelector('form') as HTMLFormElement)
    await waitFor(() =>
      expect(
        screen.getByText('重连退避上限（retry_ms）必须在 0-60000 之间')
      ).toBeInTheDocument()
    )
    expect(saveMock).not.toHaveBeenCalled()
  })

  it('上传接口未上线 → 报错如实展示，不回填假 object_key', async () => {
    renderDialog({ ...BASE_API, protocol: 'grpc', streaming: false })
    openRequestTab()
    const fileInput = screen.getByLabelText('选择 .proto 文件')
    const file = new File(['syntax = "proto3";'], 'demo.proto', { type: 'text/plain' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() =>
      expect(screen.getByText(/上传失败：Failed to fetch 404/)).toBeInTheDocument()
    )
    expect(screen.getByLabelText('proto_object_key')).toHaveValue('')
  })
})
