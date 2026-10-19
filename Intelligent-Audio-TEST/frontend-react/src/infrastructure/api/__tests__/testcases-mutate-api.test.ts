/**
 * testcases create/update 写接口单测（接线卡 INT-922 P1-1）：
 * POST /testcases / PUT /testcases/{id} 的 snake_case 顶层映射契约
 * （对照 api_gateway/schemas/testcase.py TestCaseCreateSchema/TestCaseUpdateSchema，
 * Vue testcasesApi.create/update 口径——config/algorithm_params 值内动态结构原样透传）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import {
  createTestCase,
  updateTestCase,
  type TestCaseMutatePayload,
} from '@/infrastructure/api/testcases-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

function lastCall(index = 0): [string, RequestInit] {
  return fetchMock.mock.calls[index] as [string, RequestInit]
}

const SAMPLE_PAYLOAD: TestCaseMutatePayload = {
  name: '接线测试-保存用例',
  description: '描述',
  groupId: 'g-1',
  tags: ['客厅', '中文'],
  algorithmType: 'voice_llm',
  config: {
    rounds: [
      {
        round_number: 1,
        audios: [{ audio_id: 101, spl: 65 }],
        evaluation: { enabled: true, dimensions: [{ id: 5, weight: 50, threshold: 80 }] },
      },
    ],
  },
  algorithmParams: [{ round_number: 1, params: [{ field_code: 'voiceprint', field_value: 'x' }] }],
  referenceParams: [{ round_number: 1, reference_params_path: 'ref.txt' }],
}

describe('testcases create/update 写接口（INT-922）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  describe('createTestCase', () => {
    it('POST /testcases 提交 snake_case 顶层请求体，返回创建 id', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: '测试用例创建成功', data: { id: 'tc-new' } }, 201)
      )
      const result = await createTestCase(SAMPLE_PAYLOAD)
      expect(result).toEqual({ id: 'tc-new' })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/testcases`)
      expect(init.method).toBe('POST')
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      expect(body).toMatchObject({
        name: '接线测试-保存用例',
        description: '描述',
        group_id: 'g-1',
        tags: ['客厅', '中文'],
        algorithm_type: 'voice_llm',
      })
      // config / algorithm_params 值内动态结构原样透传（snake_case 契约）
      expect(body.config).toMatchObject({
        rounds: [
          {
            round_number: 1,
            audios: [{ audio_id: 101, spl: 65 }],
            evaluation: { enabled: true, dimensions: [{ id: 5, weight: 50, threshold: 80 }] },
          },
        ],
      })
      expect(body.algorithm_params).toEqual([
        { round_number: 1, params: [{ field_code: 'voiceprint', field_value: 'x' }] },
      ])
      expect(body.reference_params).toEqual([
        { round_number: 1, reference_params_path: 'ref.txt' },
      ])
    })

    it('strategy_id / strategy_overrides 顶层 snake_case 映射', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: '测试用例创建成功', data: { id: 'tc-2' } }, 201)
      )
      await createTestCase({
        ...SAMPLE_PAYLOAD,
        strategyId: 'str-9',
        strategyOverrides: { backgroundNoise: { audioId: 7, spl: 60 } },
      })
      const body = JSON.parse(String(lastCall()[1].body)) as Record<string, unknown>
      expect(body).toMatchObject({
        strategy_id: 'str-9',
        strategy_overrides: { backgroundNoise: { audioId: 7, spl: 60 } },
      })
    })

    it('新建分组：group 缺省时仅传 group（无 group_id）', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: '测试用例创建成功', data: { id: 'tc-3' } }, 201)
      )
      await createTestCase({ name: '新组用例', group: '新分组' })
      const body = JSON.parse(String(lastCall()[1].body)) as Record<string, unknown>
      expect(body).toMatchObject({ name: '新组用例', group: '新分组' })
      expect(body.group_id).toBeUndefined()
    })
  })

  describe('updateTestCase', () => {
    it('PUT /testcases/{id} 提交 snake_case 顶层请求体', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: '测试用例更新成功' })
      )
      await updateTestCase('tc-1', SAMPLE_PAYLOAD)
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/testcases/tc-1`)
      expect(init.method).toBe('PUT')
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      expect(body).toMatchObject({
        name: '接线测试-保存用例',
        group_id: 'g-1',
        algorithm_type: 'voice_llm',
      })
      expect(body.config).toMatchObject({
        rounds: [{ round_number: 1, evaluation: { enabled: true } }],
      })
    })

    it('清引用契约：strategy_id 显式空字符串透传（null 原样保留，不 undefined 化）', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: '测试用例更新成功' })
      )
      await updateTestCase('tc-1', {
        ...SAMPLE_PAYLOAD,
        strategyId: '',
        strategyOverrides: null,
      })
      const body = JSON.parse(String(lastCall()[1].body)) as Record<string, unknown>
      expect(body).toMatchObject({ strategy_id: '' })
      expect(body.strategy_overrides).toBeNull()
    })

    it('undefined 字段不进入请求体（exclude_none 契约对齐）', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: '测试用例更新成功' })
      )
      await updateTestCase('tc-1', {
        name: '仅改名',
        description: null,
        groupId: undefined,
        algorithmType: undefined,
        config: undefined,
      })
      const body = JSON.parse(String(lastCall()[1].body)) as Record<string, unknown>
      expect(body).toMatchObject({ name: '仅改名', description: null })
      expect(body.group_id).toBeUndefined()
      expect(body.algorithm_type).toBeUndefined()
      expect(body.config).toBeUndefined()
    })
  })
})
