/**
 * T4.2：API 编辑弹窗「参数配置」页签（API 实例作用域 + 策略绑定）。
 * 覆盖：页签合并（无输出字段/映射页签、无「算法类型级声明」横幅）、
 * 策略下拉绑定、覆盖行可编辑保存、403 降级、新建 API / 未选算法降级。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiConfig } from '@/domain/models/apiConfig'
import type { ParamProfile } from '@/domain/models/paramProfile'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  toAlgorithmApiMapping,
  toAlgorithmApiParam,
} from '@/infrastructure/dto/api-algorithm-readonly.dto'

const {
  saveMock,
  fetchApiMock,
  paramsMock,
  mappingsMock,
  dimensionsMock,
  listProfilesMock,
  bindMock,
  saveOverridesMock,
  createProfileMock,
  cloneProfileMock,
  algorithmOptions,
} = vi.hoisted(() => ({
  algorithmOptions: { list: [] as Array<{ id: string; name: string }> },
  saveMock: vi.fn(async (_input: Record<string, unknown>): Promise<boolean> => true),
  fetchApiMock: vi.fn(async (_id: number): Promise<unknown> => null),
  paramsMock: vi.fn(async (_algorithmType: string, _apiId: number): Promise<unknown[]> => []),
  mappingsMock: vi.fn(async (_algorithmType: string, _apiId: number): Promise<unknown[]> => []),
  dimensionsMock: vi.fn(async (): Promise<unknown[]> => []),
  listProfilesMock: vi.fn(
    async (
      _algorithmType?: string,
      _scope?: string
    ): Promise<{ profiles: unknown[]; bindings: unknown[] }> => ({ profiles: [], bindings: [] })
  ),
  bindMock: vi.fn(async (_apiId: number, _profileId: number | null) => ({
    apiId: 21,
    profileId: 12,
  })),
  saveOverridesMock: vi.fn(async (_apiId: number, _input: unknown) => ({
    paramsCreated: 2,
    paramsUpdated: 0,
    paramsDeleted: 0,
    mappingsCreated: 1,
    mappingsUpdated: 0,
    mappingsDeleted: 0,
  })),
  createProfileMock: vi.fn(async () => ({})),
  cloneProfileMock: vi.fn(async () => ({})),
}))

vi.mock('@/application/test-execution/useApisCrud', () => ({
  useApisCrud: () => ({ save: saveMock }),
}))

vi.mock('@/infrastructure/api/test-execution-api', () => ({
  fetchApi: fetchApiMock,
  parseApiResponsePreview: vi.fn(),
  uploadApiProto: vi.fn(),
}))

vi.mock('@/application/test-execution/useTestAlgorithmOptions', () => ({
  useTestAlgorithmOptions: () => ({ data: algorithmOptions.list }),
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({
    user: null,
    hasPermission: () => true,
    hasAnyPermission: () => true,
  }),
}))

vi.mock('@/infrastructure/api/api-algorithm-readonly-api', () => ({
  fetchAlgorithmApiParams: paramsMock,
  fetchAlgorithmApiMappings: mappingsMock,
}))

vi.mock('@/infrastructure/api/evaluation-api', () => ({
  fetchEvaluationDimensions: dimensionsMock,
}))

vi.mock('@/infrastructure/api/param-profile-api', () => ({
  listProfiles: listProfilesMock,
  getProfile: vi.fn(),
  createProfile: createProfileMock,
  updateProfile: vi.fn(),
  deleteProfile: vi.fn(),
  cloneProfile: cloneProfileMock,
  bindApiProfile: bindMock,
  saveApiScopeOverrides: saveOverridesMock,
}))

import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'

import { ApiEditDialog } from '../api-edit-dialog'

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
  endpoints: [],
  maxConcurrent: 5,
  protocol: 'http',
  streaming: false,
  meta: { version: 'v1', appendix_test: 1 },
  audioConfig: null,
}

const PROFILE_FIXTURE: ParamProfile = {
  id: 12,
  scope: 'api',
  algorithmType: 'voice_llm',
  name: 'ASR 输出策略',
  description: null,
  status: 'online',
  clonedFrom: null,
  params: [],
  mappings: [],
  createdAt: null,
  updatedAt: null,
}

/** 后端 api-scope 解析结果（策略 + 实例覆盖；无算法类型级默认层） */
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

function renderDialog(api?: ApiConfig) {
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
  algorithmOptions.list = []
  useAlgorithmStore.setState({ algorithmId: '' })
  paramsMock.mockReset()
  mappingsMock.mockReset()
  dimensionsMock.mockReset()
  listProfilesMock.mockReset()
  bindMock.mockReset()
  saveOverridesMock.mockReset()
  createProfileMock.mockReset()
  cloneProfileMock.mockReset()

  paramsMock.mockResolvedValue(RAW_PARAMS.map(toAlgorithmApiParam))
  mappingsMock.mockResolvedValue(RAW_MAPPINGS.map(toAlgorithmApiMapping))
  dimensionsMock.mockResolvedValue([{ id: 72, name: '准确率' }])
  listProfilesMock.mockResolvedValue({
    profiles: [PROFILE_FIXTURE],
    bindings: [{ apiId: 21, profileId: 12 }],
  })
  bindMock.mockResolvedValue({ apiId: 21, profileId: 12 })
})

describe('页签合并（T4.2）', () => {
  it('只有 基础/请求模板/响应解析/参数配置 四个页签，且无「算法类型级声明」横幅', async () => {
    renderDialog(API_FIXTURE)
    expect(screen.getByRole('tab', { name: '参数配置' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '输出字段' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '映射' })).not.toBeInTheDocument()
    openTab('参数配置')
    await waitFor(() => expect(paramsMock).toHaveBeenCalledWith('voice_llm', 21))
    expect(document.body.textContent).not.toContain('算法类型级声明，本类型下所有 API 共用')
  })

  it('响应解析页签的 C0 判定改为按 API 实例（策略 + 覆盖）解析结果', async () => {
    renderDialog(API_FIXTURE)
    openTab('响应解析')
    expect(
      await screen.findByText('该 API 已声明 2 个输出字段 → 本页解析器不兜底')
    ).toBeInTheDocument()
  })
})

describe('参数配置页签', () => {
  it('展示本 API 的 output 字段与映射（可编辑行，input 行不出现）', async () => {
    renderDialog(API_FIXTURE)
    openTab('参数配置')

    expect(await screen.findByDisplayValue('response_audio')).toBeInTheDocument()
    expect(screen.getByDisplayValue('data.items[0].text')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('input_text')).not.toBeInTheDocument()
    expect(screen.getAllByDisplayValue('asr_text').length).toBeGreaterThan(0)
    expect(await screen.findByText('准确率')).toBeInTheDocument()
  })

  it('打开弹窗回读已绑定策略：下拉回显策略名而非「未绑定」', async () => {
    renderDialog(API_FIXTURE)
    openTab('参数配置')

    const select = await screen.findByRole('combobox', { name: '参数策略' })
    await waitFor(() => expect(listProfilesMock).toHaveBeenCalledWith('voice_llm', 'api'))
    await waitFor(() => expect(select.textContent).toContain('ASR 输出策略'))
    expect(select.textContent).not.toContain('未绑定')
  })

  it('切换策略下拉即 PUT binding', async () => {
    const user = userEvent.setup()
    // 当前 API 未绑定 → 选择策略触发绑定
    listProfilesMock.mockResolvedValue({ profiles: [PROFILE_FIXTURE], bindings: [] })
    renderDialog(API_FIXTURE)
    openTab('参数配置')

    const select = await screen.findByRole('combobox', { name: '参数策略' })
    await waitFor(() => expect(listProfilesMock).toHaveBeenCalledWith('voice_llm', 'api'))
    await user.click(select)
    await user.click(await screen.findByText('ASR 输出策略'))

    await waitFor(() => expect(bindMock).toHaveBeenCalledWith(21, 12))
  })

  it('保存参数配置 → PUT overrides（body 只含 output 字段与 api 映射）', async () => {
    renderDialog(API_FIXTURE)
    openTab('参数配置')
    await screen.findByDisplayValue('response_audio')

    fireEvent.click(screen.getByRole('button', { name: '保存参数配置' }))

    await waitFor(() => expect(saveOverridesMock).toHaveBeenCalledTimes(1))
    const [, payload] = saveOverridesMock.mock.calls[0]
    expect(payload).toMatchObject({ algorithmType: 'voice_llm' })
    const params = (payload as { params: Array<{ paramCode: string; direction: string }> }).params
    expect(params.map((p) => [p.paramCode, p.direction])).toEqual([
      ['response_audio', 'output'],
      ['asr_text', 'output'],
    ])
    const mappings = (payload as { mappings: Array<{ source: string }> }).mappings
    expect(mappings.map((m) => m.source)).toEqual(['api'])
  })

  it('删除输出字段后保存：该行不再提交', async () => {
    renderDialog(API_FIXTURE)
    openTab('参数配置')
    await screen.findByDisplayValue('response_audio')

    const deleteButtons = screen.getAllByRole('button', { name: '删除输出字段' })
    fireEvent.click(deleteButtons[0])
    fireEvent.click(screen.getByRole('button', { name: '保存参数配置' }))

    await waitFor(() => expect(saveOverridesMock).toHaveBeenCalledTimes(1))
    const payload = saveOverridesMock.mock.calls[0][1] as {
      params: Array<{ paramCode: string }>
    }
    expect(payload.params.map((p) => p.paramCode)).toEqual(['asr_text'])
  })

  it('另存为新策略 → POST create 后绑定新策略', async () => {
    const user = userEvent.setup()
    createProfileMock.mockResolvedValue({ ...PROFILE_FIXTURE, id: 99, name: '新策略' })
    renderDialog(API_FIXTURE)
    openTab('参数配置')
    await screen.findByDisplayValue('response_audio')

    await user.click(screen.getByRole('button', { name: '另存为新策略' }))
    fireEvent.change(screen.getByLabelText('策略名称 *'), { target: { value: '新策略' } })
    fireEvent.click(screen.getByRole('button', { name: '确定' }))

    await waitFor(() => expect(createProfileMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(bindMock).toHaveBeenCalledWith(21, 99))
  })

  it('algorithm:read 403 → 页签「无权查看参数配置」，不影响保存', async () => {
    paramsMock.mockRejectedValue(new ApiError({ httpStatus: 403, message: 'forbidden' }))
    renderDialog(API_FIXTURE)
    openTab('参数配置')
    expect(await screen.findByText('无权查看参数配置')).toBeInTheDocument()

    openTab('基础')
    fireEvent.change(screen.getByLabelText('API 名称 *'), {
      target: { value: '接线测试_可保存' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    expect(saveMock.mock.calls[0][0].name).toBe('接线测试_可保存')
  })
})

describe('降级口径', () => {
  it('新建 API（无 id）→ 可直接配置参数，且不发参数/映射读请求（策略列表照拉）', async () => {
    // 新建 API 的算法类型来自全局算法（此处显式预设，避免先命中「未选择关联算法」）
    algorithmOptions.list = [{ id: 'voice_llm', name: '小艺语音大模型' }]
    useAlgorithmStore.setState({ algorithmId: 'voice_llm' })
    renderDialog(undefined)
    openTab('参数配置')
    expect(await screen.findByText('新建 API：现在就能配参数')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新增输出字段' })).toBeEnabled()
    expect(paramsMock).not.toHaveBeenCalled()
    expect(mappingsMock).not.toHaveBeenCalled()
    // 新建态也要能「套用配置策略」，故按算法类型拉取策略列表（与 apiId 无关）
    await waitFor(() => expect(listProfilesMock).toHaveBeenCalledWith('voice_llm', 'api'))
  })

  it('新建 API：参数草稿随底部「保存」一并提交（无需先保存再回来配）', async () => {
    algorithmOptions.list = [{ id: 'voice_llm', name: '小艺语音大模型' }]
    useAlgorithmStore.setState({ algorithmId: 'voice_llm' })
    renderDialog(undefined)
    openTab('参数配置')

    fireEvent.click(screen.getByRole('button', { name: '新增输出字段' }))
    fireEvent.change(screen.getByLabelText('参数代码'), { target: { value: 'asr_text' } })

    openTab('基础')
    fireEvent.change(screen.getByLabelText('API 名称 *'), { target: { value: '新建_API' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    const call = saveMock.mock.calls[0] as unknown as [
      Record<string, unknown>,
      { algorithmType: string; params: Array<{ paramCode: string; direction: string }> },
    ]
    expect(call[1].algorithmType).toBe('voice_llm')
    expect(call[1].params.map((p) => [p.paramCode, p.direction])).toEqual([
      ['asr_text', 'output'],
    ])
  })

  it('未选择关联算法 → 策略下拉与保存禁用并提示', () => {
    renderDialog({ ...API_FIXTURE, algorithmType: null })
    openTab('参数配置')
    expect(screen.getByText('未选择关联算法')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '参数策略' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '保存参数配置' })).toBeDisabled()
    expect(paramsMock).not.toHaveBeenCalled()
  })
})
