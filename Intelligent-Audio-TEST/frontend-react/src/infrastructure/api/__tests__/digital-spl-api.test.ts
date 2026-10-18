/**
 * digital-spl-api 真实接口单测（接线卡 INT-649）：
 * 列表/API 引用 URL 与 per_page 契约、读侧 calibration_points 平铺点集映射、
 * 创建/编辑/删除/校准/设默认请求体 snake_case 契约。fetch 走统一 client（INT-605 基座）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import {
  calibrateDigitalSplMapping,
  createDigitalSplMapping,
  deleteDigitalSplMapping,
  fetchApiRefs,
  fetchDigitalSplMappings,
  setDefaultDigitalSplMapping,
  updateDigitalSplMapping,
} from '@/infrastructure/api/digital-spl-api'
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

const DIGITAL_ITEM = {
  id: 21,
  api_id: 101,
  name: '客服ASR_WebSocket_默认',
  description: '描述',
  vendor: 'volc_ast',
  protocol: 'websocket',
  reference_spl: 65,
  reference_gain_linear: 1.0,
  calibration_status: 'calibrated',
  calibration_points: [
    { target_spl: 45, gain_linear: 0.316, rms_dbfs: -60 },
    { target_spl: 65, gain_linear: 1.0, rms_dbfs: -50 },
  ],
  min_gain_linear: 0.001,
  max_gain_linear: 10.0,
  created_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-10-11T15:30:00Z',
}

describe('digital-spl-api 真实接口（INT-649）', () => {
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

  describe('fetchDigitalSplMappings', () => {
    it('GET /digital-spl 带 per_page=100，读侧 calibration_points 映射 calibrationPoints', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: { items: [DIGITAL_ITEM], total: 1, page: 1, per_page: 100, pages: 1 },
        })
      )
      const rows = await fetchDigitalSplMappings()
      expect(rows).toHaveLength(1)
      expect(rows[0]).toMatchObject({
        id: 21,
        apiId: 101,
        name: '客服ASR_WebSocket_默认',
        vendor: 'volc_ast',
        protocol: 'websocket',
        referenceSpl: 65,
        referenceGainLinear: 1.0,
        calibrationStatus: 'calibrated',
        minGainLinear: 0.001,
        maxGainLinear: 10.0,
        calibrationPoints: [
          { targetSpl: 45, gainLinear: 0.316, rmsDbfs: -60 },
          { targetSpl: 65, gainLinear: 1.0, rmsDbfs: -50 },
        ],
      })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/digital-spl?page=1&per_page=100`)
      expect(init.method).toBe('GET')
    })
  })

  describe('fetchApiRefs', () => {
    it('GET /apis 带 per_page=100，rms_spl_mapping_id 映射 rmsSplMappingId', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: {
            items: [
              { id: 3, name: 'INT95R7-voice-llm-adapter', vendor: 'custom', rms_spl_mapping_id: null },
              { id: 101, name: '客服ASR', vendor: 'volc_ast', rms_spl_mapping_id: 21 },
            ],
            total: 2,
          },
        })
      )
      const refs = await fetchApiRefs()
      expect(refs).toEqual([
        { id: 3, name: 'INT95R7-voice-llm-adapter', vendor: 'custom', protocol: null, rmsSplMappingId: null },
        { id: 101, name: '客服ASR', vendor: 'volc_ast', protocol: null, rmsSplMappingId: 21 },
      ])
      const [url] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/apis?page=1&per_page=100`)
    })
  })

  describe('createDigitalSplMapping', () => {
    it('POST /digital-spl 提交 snake_case 请求体（calibration_data.points），返回 IdData', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: 'RMS→SPL 映射创建成功', data: { id: 25 } }, 201)
      )
      const result = await createDigitalSplMapping({
        apiId: 101,
        name: '新映射',
        description: null,
        vendor: 'volc_ast',
        protocol: 'websocket',
        referenceSpl: 65,
        referenceGainLinear: 1.0,
        calibrationStatus: null,
        calibrationPoints: [
          { targetSpl: 45, gainLinear: 0.316, rmsDbfs: -60 },
          { targetSpl: 65, gainLinear: 1.0, rmsDbfs: -50 },
        ],
        minGainLinear: 0.001,
        maxGainLinear: 10.0,
      })
      expect(result).toEqual({ id: 25 })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/digital-spl`)
      expect(init.method).toBe('POST')
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      expect(body).toMatchObject({
        api_id: 101,
        name: '新映射',
        reference_spl: 65,
        reference_gain_linear: 1.0,
        min_gain_linear: 0.001,
        max_gain_linear: 10.0,
        calibration_data: {
          points: [
            { target_spl: 45, gain_linear: 0.316, rms_dbfs: -60 },
            { target_spl: 65, gain_linear: 1.0, rms_dbfs: -50 },
          ],
        },
      })
    })
  })

  describe('updateDigitalSplMapping', () => {
    it('PUT /digital-spl/{id} 提交 snake_case 请求体', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: 'RMS→SPL 映射更新成功' })
      )
      await updateDigitalSplMapping(21, {
        name: '改名',
        referenceSpl: 70,
        calibrationStatus: null,
      })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/digital-spl/21`)
      expect(init.method).toBe('PUT')
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      expect(body).toMatchObject({ name: '改名', reference_spl: 70 })
    })
  })

  describe('deleteDigitalSplMapping', () => {
    it('DELETE /digital-spl/{id} 成功返回 { success: true }', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: 'RMS→SPL 映射已删除' })
      )
      const result = await deleteDigitalSplMapping(21)
      expect(result).toEqual({ success: true })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/digital-spl/21`)
      expect(init.method).toBe('DELETE')
    })
  })

  describe('calibrateDigitalSplMapping', () => {
    it('POST /digital-spl/{id}/calibrate 提交 calibration_data.points 全量替换', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          message: '校准完成',
          data: { id: 21, calibration_status: 'calibrated' },
        })
      )
      const result = await calibrateDigitalSplMapping(21, [
        { targetSpl: 45, gainLinear: 0.316, rmsDbfs: -60 },
        { targetSpl: 65, gainLinear: 1.0, rmsDbfs: -50 },
      ])
      expect(result).toEqual({ success: true })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/digital-spl/21/calibrate`)
      expect(init.method).toBe('POST')
      const body = JSON.parse(String(init.body)) as {
        calibration_data: { points: unknown[] }
      }
      expect(body).toMatchObject({
        calibration_data: {
          points: [
            { target_spl: 45, gain_linear: 0.316, rms_dbfs: -60 },
            { target_spl: 65, gain_linear: 1.0, rms_dbfs: -50 },
          ],
        },
      })
    })

    it('409 冲突：ApiError httpStatus=409 承载（分布式锁互斥）', async () => {
      queueResponses(
        jsonResponse(
          { success: false, code: 204, message: 'API 正在执行校准，请稍后再试', detail: 'API 正在执行校准，请稍后再试' },
          409
        )
      )
      const error = await calibrateDigitalSplMapping(21, [
        { targetSpl: 65, gainLinear: 1.0, rmsDbfs: -50 },
      ]).catch((e: unknown) => e)
      expect((error as { httpStatus: number }).httpStatus).toBe(409)
    })
  })

  describe('setDefaultDigitalSplMapping', () => {
    it('POST /digital-spl/by-api/{apiId}/set-default 提交 mapping_id', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          message: '默认映射已更新',
          data: { api_id: 3, rms_spl_mapping_id: 11 },
        })
      )
      const result = await setDefaultDigitalSplMapping(3, 11)
      expect(result).toEqual({ success: true })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/digital-spl/by-api/3/set-default`)
      expect(JSON.parse(String(init.body))).toEqual({ mapping_id: 11 })
    })

    it('mapping_id null：清除默认映射', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          message: '默认映射已更新',
          data: { api_id: 3, rms_spl_mapping_id: null },
        })
      )
      await setDefaultDigitalSplMapping(3, null)
      expect(JSON.parse(String(lastCall()[1].body))).toEqual({ mapping_id: null })
    })
  })
})
