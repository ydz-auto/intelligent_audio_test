/**
 * INT-1778：API 编辑弹窗后三个页签（母卡 INT-1750 §2.3 / §2.4 / §2.5）。
 * 覆盖：响应解析 8 键可填 + C0 裁定口径提示 + 非法 JSON 拦截；
 * 输出字段 / 映射只读 + 算法类型级横幅 + 去算法配置跳转；
 * `algorithm:read` 403 降级不阻断保存。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiConfig } from '@/domain/models/apiConfig'
import { ApiError } from '@/infrastructure/api/api-error'

const { saveMock, fetchApiMock, paramsMock, mappingsMock, navigateMock, dimensionsMock } =
  vi.hoisted(() => ({
    // INT-1939：save 返回成否，弹窗据此决定关不关
    saveMock: vi.fn(async (_input: Record<string, unknown>): Promise<boolean> => true),
    fetchApiMock: vi.fn(async (_id: number): Promise<unknown> => null),
    paramsMock: vi.fn(async (_algorithmType: string): Promise<unknown[]> => []),
    mappingsMock: vi.fn(async (_algorithmType: string): Promise<unknown[]> => []),
    navigateMock: vi.fn(() => Promise.resolve()),
    dimensionsMock: vi.fn(async (): Promise<unknown[]> => []),
  }))

vi.mock('@/application/test-execution/useApisCrud', () => ({
  useApisCrud: () => ({ save: saveMock }),
}))

vi.mock('@/infrastructure/api/test-execution-api', () => ({
  fetchApi: fetchApiMock,
}))

vi.mock('@/application/test-execution/useTestAlgorithmOptions', () => ({
  useTestAlgorithmOptions: () => ({ data: [] }),
}))

vi.mock('@/infrastructure/api/api-algorithm-readonly-api', () => ({
  fetchAlgorithmApiParams: paramsMock,
  fetchAlgorithmApiMappings: mappingsMock,
}))

vi.mock('@/infrastructure/api/evaluation-api', () => ({
  fetchEvaluationDimensions: dimensionsMock,
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

import { ApiEditDialog } from '../api-edit-dialog'
import { toAlgorithmApiMapping, toAlgorithmApiParam } from '@/infrastructure/dto/api-algorithm-readonly.dto'

const API_FIXTURE: ApiConfig = {
  id: 21,
  name: '接线测试_API',
  vendor: null,
  description: null,
  status: 'online',
  algorithmType: 'voice_llm',
  defaultMaxProcess: 5,
  defaultMaxTimeout: 30,
  defaultMaxAudioDuration: 60,
  healthScore: 100,
  endpoints: [
    {
      id: 'ep-1',
      endpoint: 'https://api.example.com/v1/asr',
      name: null,
      maxProcess: 5,
      maxTimeout: 30,
      maxAudioDuration: 60,
      priority: 1,
      status: 'online',
      healthScore: 100,
      description: null,
      apiKeysSummary: null,
    },
  ],
  maxConcurrent: 5,
  protocol: 'http',
  streaming: false,
  meta: { version: 'v1', appendix_test: 1 },
  audioConfig: null,
}

/** 后端 `/algorithm/params` 原始行（走真实 DTO 转换，覆盖 field_path 契约） */
const RAW_PARAMS = [
  { id: 7, param_code: 'input_text', param_type: 'text', direction: 'input', field_path: null },
  {
    id: 9,
    param_code: 'response_audio',
    param_type: 'audio_file',
    direction: 'output',
    field_path: null,
    label: null,
  },
  {
    id: 10,
    param_code: 'asr_text',
    param_type: 'text',
    direction: 'output',
    field_path: 'data.items[0].text',
    label: 'ASR 文本',
  },
]

const RAW_MAPPINGS = [
  {
    id: 1711,
    source: 'api',
    source_param: 'asr_text',
    source_direction: 'output',
    dimension_id: 72,
    target_param: 'text',
    transform_type: 'none',
  },
]

function renderDialog(api: ApiConfig = API_FIXTURE) {
  fetchApiMock.mockResolvedValue(null)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ApiEditDialog open onOpenChange={vi.fn()} api={api} />
    </QueryClientProvider>
  )
}

function openTab(label: string) {
  fireEvent.click(screen.getByRole('tab', { name: label }))
}

beforeEach(() => {
  saveMock.mockClear()
  fetchApiMock.mockClear()
  paramsMock.mockReset()
  mappingsMock.mockReset()
  navigateMock.mockClear()
  dimensionsMock.mockReset()
  paramsMock.mockResolvedValue(RAW_PARAMS.map(toAlgorithmApiParam))
  mappingsMock.mockResolvedValue(RAW_MAPPINGS.map(toAlgorithmApiMapping))
  dimensionsMock.mockResolvedValue([{ id: 72, name: '准确率' }])
})

describe('响应解析页签（INT-1778 §2.3）', () => {
  it('8 个键齐全 + C0 裁定口径提示 + 已声明输出字段的判定', async () => {
    renderDialog()
    openTab('响应解析')

    expect(screen.getAllByText(/C0 裁定口径/).length).toBeGreaterThan(0)
    expect(screen.getByLabelText('响应解析器（result_parser）')).toBeInTheDocument()
    for (const label of [
      'ASR 文本映射（asr_mapping）',
      '翻译文本映射（trans_mapping）',
      '句结束标志（sentence_end_mapping）',
      '会话结束标志（session_end_mapping）',
      '业务错误码（error_code_mapping）',
      '业务错误信息（error_msg_mapping）',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
    expect(
      screen.getByRole('combobox', { name: '流式结果拼接（append_mode）' })
    ).toBeInTheDocument()

    // 判定依据 = 同一次 /algorithm/params?param_type=api 有 direction=output 行
    expect(
      await screen.findByText('该类型已声明 2 个输出字段 → 本页解析器不兜底')
    ).toBeInTheDocument()
    expect(paramsMock).toHaveBeenCalledWith('voice_llm')
  })

  it('算法类型零输出字段 → 判定为 meta 兜底', async () => {
    paramsMock.mockResolvedValue([])
    renderDialog()
    openTab('响应解析')
    expect(
      await screen.findByText('该类型未声明输出字段 → 解析走本页 meta 兜底')
    ).toBeInTheDocument()
  })

  it('非法 JSON 拦截保存：请求不发、弹窗不关、停在响应解析页签', async () => {
    renderDialog()
    openTab('响应解析')
    fireEvent.change(screen.getByLabelText('响应解析器（result_parser）'), {
      target: { value: '{bad json' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('响应解析器 JSON 格式不正确')).toBeInTheDocument()
    expect(saveMock).not.toHaveBeenCalled()
    expect(screen.getByRole('tab', { name: '响应解析' }).getAttribute('aria-selected')).toBe('true')
  })

  it('保存提交 base 合并后的整对象（含 append_mode 布尔与未知键保留）', async () => {
    const user = userEvent.setup()
    renderDialog()
    openTab('响应解析')
    fireEvent.change(screen.getByLabelText('ASR 文本映射（asr_mapping）'), {
      target: { value: 'data.asr.text' },
    })
    await user.click(screen.getByRole('combobox', { name: '流式结果拼接（append_mode）' }))
    await user.click(await screen.findByText('是（逐句结束追加拼接）'))
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    expect(saveMock.mock.calls[0][0].meta).toEqual({
      version: 'v1',
      appendix_test: 1,
      asr_mapping: 'data.asr.text',
      append_mode: true,
    })
  })

  it('未触碰 meta 时只改名称 → 请求体不带 meta（响应解析页签同样遵守 dirty 才发）', async () => {
    renderDialog()
    openTab('响应解析')
    openTab('基础')
    fireEvent.change(screen.getByLabelText('API 名称 *'), { target: { value: '接线测试_改名' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    expect('meta' in saveMock.mock.calls[0][0]).toBe(false)
  })
})

describe('输出字段页签（INT-1778 §2.4，只读）', () => {
  it('只显示 direction=output 行，列 = param_code / param_type / field_path / label', async () => {
    renderDialog()
    openTab('输出字段')

    expect(await screen.findByText('response_audio')).toBeInTheDocument()
    expect(screen.queryByText('input_text')).not.toBeInTheDocument()
    expect(screen.getByText('data.items[0].text')).toBeInTheDocument()
    expect(screen.getByText('ASR 文本')).toBeInTheDocument()

    const rows = screen.getAllByRole('row')
    // 表头 + 2 行
    expect(rows).toHaveLength(3)
    // field_path 未落库显示「—」
    expect(within(rows[1]).getAllByText('—').length).toBeGreaterThan(0)
    // 算法类型级横幅
    expect(screen.getByText(/算法类型级声明，本类型下所有 API 共用/)).toBeInTheDocument()
  })

  it('「去算法配置」跳转可点', async () => {
    renderDialog()
    openTab('输出字段')
    fireEvent.click(await screen.findByRole('button', { name: /去算法配置/ }))
    expect(navigateMock).toHaveBeenCalledWith({ to: '/AlgorithmConfig' })
  })

  it('无 output 声明 → 空态指向响应解析页签兜底', async () => {
    paramsMock.mockResolvedValue([])
    renderDialog()
    openTab('输出字段')
    expect(
      await screen.findByText('该算法类型未声明输出字段，解析走 meta 兜底（见响应解析页签）。')
    ).toBeInTheDocument()
  })

  it('algorithm:read 返回 403 → 只读页签降级，且不影响保存', async () => {
    paramsMock.mockRejectedValue(new ApiError({ httpStatus: 403, message: 'forbidden' }))
    renderDialog()
    openTab('输出字段')
    expect(await screen.findByText('无权查看算法配置')).toBeInTheDocument()
    // 跳转按钮在无权限时隐藏
    expect(screen.queryByRole('button', { name: /去算法配置/ })).not.toBeInTheDocument()
    // 返工 P3：按钮隐藏后横幅尾句不能再说「维护入口在算法配置页」
    expect(document.body.textContent).toContain('当前账号不可查看')
    expect(document.body.textContent).not.toContain('维护入口在算法配置页')

    openTab('基础')
    fireEvent.change(screen.getByLabelText('API 名称 *'), { target: { value: '接线测试_可保存' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    expect(saveMock.mock.calls[0][0].name).toBe('接线测试_可保存')
  })
})

describe('映射页签（INT-1778 §2.5，只读，唯一数据源 /algorithm/mappings）', () => {
  it('展示 source=api 行：源参数 → 目标维度 / 目标参数 / 转换', async () => {
    renderDialog()
    openTab('映射')

    expect(await screen.findByText('asr_text')).toBeInTheDocument()
    expect(await screen.findByText('准确率')).toBeInTheDocument()
    expect(screen.getByText('text')).toBeInTheDocument()
    expect(screen.getByText('none')).toBeInTheDocument()
    expect(mappingsMock).toHaveBeenCalledWith('voice_llm')
    expect(screen.getByText(/算法类型级声明，本类型下所有 API 共用/)).toBeInTheDocument()
  })

  it('维度名取不到时回落到 #dimensionId（不显示空白）', async () => {
    dimensionsMock.mockResolvedValue([])
    renderDialog()
    openTab('映射')
    expect(await screen.findByText('#72')).toBeInTheDocument()
  })

  it('无 source=api 映射 → 空态提示去算法配置页新增', async () => {
    mappingsMock.mockResolvedValue([])
    renderDialog()
    openTab('映射')
    expect(
      await screen.findByText('该算法类型未配置来源为 API 输出的映射')
    ).toBeInTheDocument()
  })
})

describe('未选关联算法', () => {
  it('输出字段 / 映射显示「未选择关联算法」空态', () => {
    renderDialog({ ...API_FIXTURE, algorithmType: null })
    openTab('输出字段')
    expect(screen.getAllByText('未选择关联算法').length).toBeGreaterThan(0)
    openTab('映射')
    expect(screen.getAllByText('未选择关联算法').length).toBeGreaterThan(1)
    // 未选算法不发算法配置请求
    expect(paramsMock).not.toHaveBeenCalled()
    expect(mappingsMock).not.toHaveBeenCalled()
  })
})
