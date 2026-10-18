/**
 * 算法配置 API 单测（infrastructure/api；INT-647 接线后真实端点契约）。
 * mock client.ts 的 request（及 evaluation-api 的 fetchDimensionOptions），断言：
 * 端点路径/方法、snake_case 请求体、INT-297 信封解包、响应 camelCase 映射；
 * §154 用例引用聚合兜底（后端未返 case_count 时经 testcases-api 拉用例计数）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/infrastructure/api/client', () => ({
  request: vi.fn(),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/infrastructure/api/evaluation-api', () => ({
  fetchDimensionOptions: vi.fn(),
}))

import { request, apiClient } from '@/infrastructure/api/client'
import { fetchDimensionOptions } from '@/infrastructure/api/evaluation-api'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  bulkDeleteAlgorithms,
  createAlgorithm,
  createAlgorithmGroup,
  deleteAlgorithm,
  deleteAlgorithmGroup,
  fetchAlgorithmDefinitions,
  fetchAlgorithmDetail,
  fetchAlgorithmGroups,
  importAlgorithms,
  publishAlgorithm,
  reloadAlgorithmConfig,
  updateAlgorithm,
  updateAlgorithmGroup,
  type SaveAlgorithmInput,
} from '@/infrastructure/api/algorithm-config-api'

const mockRequest = request as unknown as ReturnType<typeof vi.fn>
const mockApiClientGet = apiClient.get as unknown as ReturnType<typeof vi.fn>
const mockFetchDimensionOptions = fetchDimensionOptions as unknown as ReturnType<typeof vi.fn>

function saveInput(type: string): SaveAlgorithmInput {
  return {
    type,
    name: `${type} 名称`,
    groupId: 1,
    displayOrder: 1,
    status: 'online',
    description: '',
    deviceParams: [{ paramCode: 'input_audio', paramName: '输入音频', direction: 'input', paramType: 'audio_file', required: true, defaultValue: '', helpText: '' }],
    apiParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions: [],
  }
}

/** AlgorithmDetailResponse 形态（snake_case 列表项） */
function definitionDto(type: string, name = `${type} 名称`): Record<string, unknown> {
  return {
    id: 1,
    type,
    name,
    group_id: 1,
    group_name: '语音识别',
    category: null,
    description: '描述',
    status: 'online',
    icon: null,
    display_order: 1,
    device_params: [
      { id: 101, param_code: 'input_audio', param_name: '输入音频', label: '输入音频', param_type: 'audio_file', direction: 'input', required: true, default_value: null, help_text: '待识别音频', ui_order: 1, hidden: false },
    ],
    api_params: [],
    case_params: [],
    reference_params: [],
    mappings: { device: [], api: [], evaluation: [] },
    associated_dimensions: [],
    created_at: '2026-08-10T08:30:00Z',
    updated_at: '2026-10-12T16:40:00Z',
  }
}

/** GET /testcases 信封（INT-297 分页信封；聚合兜底只消费 total，items 可为空） */
function testcasesEnvelope(
  total: number,
  items: unknown[] = []
): Record<string, unknown> {
  return { items, total, page: 1, per_page: 1, pages: Math.max(1, Math.ceil(total / 1)) }
}

describe('algorithm-config-api（真实端点接线）', () => {
  beforeEach(() => {
    mockRequest.mockReset()
    mockApiClientGet.mockReset()
    mockFetchDimensionOptions.mockReset()
    mockFetchDimensionOptions.mockResolvedValue([])
  })

  it('fetchAlgorithmDefinitions 走 GET /algorithm/definitions 并解 INT-297 信封', async () => {
    mockRequest.mockResolvedValue({
      items: [definitionDto('asr-v3')],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })
    // 后端无 case_count → 触发聚合兜底，用例库为空
    mockApiClientGet.mockResolvedValue(testcasesEnvelope(0))
    const list = await fetchAlgorithmDefinitions()
    expect(mockRequest).toHaveBeenCalledWith('GET', '/algorithm/definitions')
    expect(mockApiClientGet).toHaveBeenCalledWith(
      '/testcases',
      expect.objectContaining({
        params: expect.objectContaining({ page: 1, per_page: 1, algorithm_type: 'asr-v3' }),
      })
    )
    expect(list).toHaveLength(1)
    expect(list[0].type).toBe('asr-v3')
    expect(list[0].name).toBe('asr-v3 名称')
    expect(list[0].groupId).toBe(1)
    expect(list[0].deviceParams[0].paramCode).toBe('input_audio')
    expect(list[0].deviceParams[0].direction).toBe('input')
    expect(list[0].caseCount).toBe(0)
  })

  it('fetchAlgorithmDefinitions 后端无 case_count 时按用例引用筛选 total 填充关联用例数', async () => {
    mockRequest.mockResolvedValue({
      items: [definitionDto('asr-v3'), definitionDto('tts-1')],
      total: 2,
      page: 1,
      per_page: 2,
      pages: 1,
    })
    mockApiClientGet.mockImplementation((_path: string, opts: { params: { algorithm_type: string } }) => {
      const type = opts.params.algorithm_type
      if (type === 'asr-v3') return Promise.resolve(testcasesEnvelope(2))
      if (type === 'tts-1') return Promise.resolve(testcasesEnvelope(1))
      return Promise.resolve(testcasesEnvelope(0))
    })
    const list = await fetchAlgorithmDefinitions()
    expect(mockApiClientGet).toHaveBeenCalledTimes(2)
    expect(list.find((a) => a.type === 'asr-v3')?.caseCount).toBe(2)
    expect(list.find((a) => a.type === 'tts-1')?.caseCount).toBe(1)
    expect(list.find((a) => a.type === 'asr-v3')?.deviceParams[0].paramCode).toBe('input_audio')
  })

  it('fetchAlgorithmDefinitions 后端返回 case_count 时直接消费、不再聚合', async () => {
    const dto = definitionDto('asr-v3')
    dto.case_count = 42
    mockRequest.mockResolvedValue({
      items: [dto],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })
    const list = await fetchAlgorithmDefinitions()
    expect(mockApiClientGet).not.toHaveBeenCalled()
    expect(list[0].caseCount).toBe(42)
  })

  it('fetchAlgorithmDefinitions 用例聚合失败时列表仍返回、关联用例归 0', async () => {
    mockRequest.mockResolvedValue({
      items: [definitionDto('asr-v3')],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })
    mockApiClientGet.mockRejectedValue(new Error('network'))
    const list = await fetchAlgorithmDefinitions()
    expect(list).toHaveLength(1)
    expect(list[0].caseCount).toBe(0)
  })

  it('fetchAlgorithmDetail 走 GET /algorithm/definitions/{type}（编辑/复制预填）', async () => {
    mockRequest.mockResolvedValue(definitionDto('asr-v3'))
    const detail = await fetchAlgorithmDetail('asr-v3')
    expect(mockRequest).toHaveBeenCalledWith('GET', '/algorithm/definitions/asr-v3')
    expect(detail?.type).toBe('asr-v3')
    expect(detail?.status).toBe('online')
  })

  it('fetchAlgorithmGroups 走 GET /algorithm/groups 并解信封', async () => {
    mockRequest.mockResolvedValue({
      items: [{ id: 1, name: '语音识别', description: 'desc', icon: null, display_order: 1, algorithm_count: 3, created_at: '2026-08-01T08:00:00Z', updated_at: '2026-09-28T10:12:00Z' }],
      total: 1,
      page: 1,
      per_page: 1,
      pages: 1,
    })
    const groups = await fetchAlgorithmGroups()
    expect(mockRequest).toHaveBeenCalledWith('GET', '/algorithm/groups')
    expect(groups).toHaveLength(1)
    expect(groups[0].name).toBe('语音识别')
    expect(groups[0].algorithmCount).toBe(3)
  })

  it('createAlgorithm 提交 snake_case 请求体并映射响应', async () => {
    mockRequest.mockResolvedValue(definitionDto('tts-new', 'tts-new 名称'))
    const created = await createAlgorithm(saveInput('tts-new'))
    expect(mockRequest).toHaveBeenCalledWith(
      'POST',
      '/algorithm/definitions',
      expect.objectContaining({
        type: 'tts-new',
        group_id: 1,
        status: 'online',
        device_params: expect.arrayContaining([
          expect.objectContaining({ param_code: 'input_audio', param_name: '输入音频' }),
        ]),
      })
    )
    expect(created.type).toBe('tts-new')
  })

  it('updateAlgorithm 走 PUT /algorithm/definitions/{type}', async () => {
    mockRequest.mockResolvedValue(definitionDto('asr-v3', '改名后的识别引擎'))
    const updated = await updateAlgorithm('asr-v3', saveInput('asr-v3'))
    expect(mockRequest).toHaveBeenCalledWith(
      'PUT',
      '/algorithm/definitions/asr-v3',
      expect.objectContaining({ name: 'asr-v3 名称' })
    )
    expect(updated.name).toBe('改名后的识别引擎')
  })

  it('deleteAlgorithm 走 DELETE 并返回 success', async () => {
    mockRequest.mockResolvedValue(undefined)
    const result = await deleteAlgorithm('asr-v3')
    expect(mockRequest).toHaveBeenCalledWith('DELETE', '/algorithm/definitions/asr-v3')
    expect(result).toEqual({ success: true })
  })

  it('bulkDeleteAlgorithms 提交 algorithm_types 并按 deleted_types 对账计数', async () => {
    mockRequest.mockResolvedValue({ deleted_types: ['tts-brand-new'], message: '' })
    const result = await bulkDeleteAlgorithms(['asr-v3', 'tts-brand-new'])
    expect(mockRequest).toHaveBeenCalledWith(
      'POST',
      '/algorithm/bulk-delete',
      { algorithm_types: ['asr-v3', 'tts-brand-new'] }
    )
    expect(result).toEqual({ successCount: 1, failedCount: 1 })
  })

  it('reloadAlgorithmConfig 走 POST /algorithm/reload 并映射 reloadTime', async () => {
    mockRequest.mockResolvedValue({ success: true, message: '', reload_time: '2026-10-17T00:00:00Z' })
    const result = await reloadAlgorithmConfig()
    expect(mockRequest).toHaveBeenCalledWith('POST', '/algorithm/reload')
    expect(result.success).toBe(true)
    expect(result.reloadTime).toBe('2026-10-17T00:00:00Z')
  })

  it('importAlgorithms 提交 { algorithms } 并返回实际导入数', async () => {
    mockRequest.mockResolvedValue({ imported: ['tts-import-a', 'tts-import-b'] })
    const result = await importAlgorithms([
      { type: 'tts-import-a' },
      { type: 'tts-import-b' },
      { type: 'asr-v3' },
    ])
    expect(mockRequest).toHaveBeenCalledWith(
      'POST',
      '/algorithm/import',
      { algorithms: [{ type: 'tts-import-a' }, { type: 'tts-import-b' }, { type: 'asr-v3' }] }
    )
    expect(result.importedCount).toBe(2)
  })

  it('分组 CRUD：create 走 POST /algorithm/groups、update 走 PUT、delete 走 DELETE', async () => {
    mockRequest.mockResolvedValue({ id: 9, name: '新分组', description: null, icon: null, display_order: 9, algorithm_count: 0, created_at: '', updated_at: '' })
    const created = await createAlgorithmGroup({ name: '新分组', description: '', icon: '', displayOrder: 9 })
    expect(mockRequest).toHaveBeenCalledWith(
      'POST',
      '/algorithm/groups',
      { name: '新分组', description: null, icon: null, display_order: 9 }
    )
    expect(created.algorithmCount).toBe(0)

    mockRequest.mockResolvedValue({ id: 9, name: '改名分组', description: null, icon: null, display_order: 9, algorithm_count: 0, created_at: '', updated_at: '' })
    const updated = await updateAlgorithmGroup(9, { name: '改名分组', description: '', icon: '', displayOrder: 9 })
    expect(mockRequest).toHaveBeenCalledWith('PUT', '/algorithm/groups/9', expect.objectContaining({ name: '改名分组' }))
    expect(updated.name).toBe('改名分组')

    mockRequest.mockResolvedValue(undefined)
    const deleted = await deleteAlgorithmGroup(9)
    expect(mockRequest).toHaveBeenCalledWith('DELETE', '/algorithm/groups/9')
    expect(deleted).toEqual({ success: true })
  })

  it('publishAlgorithm 新建走 GET 探测(400-not-found) + POST 创建；存量走 PUT 更新', async () => {
    // 新建：GET detail 返回 400 + 「Algorithm not found」（网关映射缺失算法语义）→ 判新 → POST 创建
    mockRequest.mockRejectedValueOnce(new ApiError({ httpStatus: 400, message: 'Algorithm not found' }))
    mockRequest.mockResolvedValueOnce(definitionDto('tts-new', 'tts-new 名称'))
    const created = await publishAlgorithm(saveInput('tts-new'))
    expect(mockRequest).toHaveBeenNthCalledWith(1, 'GET', '/algorithm/definitions/tts-new')
    expect(mockRequest).toHaveBeenNthCalledWith(2, 'POST', '/algorithm/definitions', expect.any(Object))
    expect(created.type).toBe('tts-new')

    // 存量：GET detail 返回定义 → PUT 更新
    mockRequest.mockReset()
    mockRequest.mockResolvedValueOnce(definitionDto('asr-v3', 'asr-v3 名称'))
    mockRequest.mockResolvedValueOnce(definitionDto('asr-v3', 'asr-v3 名称'))
    const updated = await publishAlgorithm(saveInput('asr-v3'))
    expect(mockRequest).toHaveBeenNthCalledWith(1, 'GET', '/algorithm/definitions/asr-v3')
    expect(mockRequest).toHaveBeenNthCalledWith(2, 'PUT', '/algorithm/definitions/asr-v3', expect.any(Object))
    expect(updated.name).toBe('asr-v3 名称')
  })
})
