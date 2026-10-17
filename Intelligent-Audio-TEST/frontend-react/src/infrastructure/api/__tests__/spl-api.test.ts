/**
 * spl-api 真实接口单测（接线卡 INT-649）：
 * 列表/统计/播放设备引用/校准历史 URL 与 per_page 契约、snake→camel 映射、
 * 创建/编辑/删除/校准请求体 snake_case 契约。fetch 走统一 client（INT-605 基座）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import {
  calibrateSplMapping,
  createSplMapping,
  deleteSplMapping,
  fetchPlaybackDeviceRefs,
  fetchSplHistory,
  fetchSplMappings,
  fetchSplStats,
  updateSplMapping,
} from '@/infrastructure/api/spl-api'
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

const SPL_ITEM = {
  id: 1,
  name: '客厅_干声_65dB_1m',
  description: '描述',
  device_id: 1,
  device: { id: 1, name: '干声测试音频接口 A' },
  device_name: '干声测试音频接口 A',
  device_model: 'UA-22',
  device_type: 'dry',
  distance: 1.0,
  target_spl: 65,
  digital_gain: 2.5,
  calibration_status: 'calibrated',
  test_frequency: 1000,
  calibration_data: {
    points: [
      { spl: 55, gain_offset: -10, digital_gain: -10, base_level: -30, final_level: -40 },
      { spl: 65, gain_offset: 0, digital_gain: 0, base_level: -30, final_level: -30 },
    ],
  },
  is_current: true,
  created_at: '2026-09-28T10:20:00Z',
  updated_at: '2026-10-10T14:05:00Z',
}

describe('spl-api 真实接口（INT-649）', () => {
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

  describe('fetchSplMappings', () => {
    it('GET /spl 带 page=1&per_page=1000，items 映射 camelCase', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: { items: [SPL_ITEM], total: 1, page: 1, per_page: 1000, pages: 1 },
        })
      )
      const rows = await fetchSplMappings()
      expect(rows).toHaveLength(1)
      expect(rows[0]).toMatchObject({
        id: 1,
        deviceId: 1,
        deviceName: '干声测试音频接口 A',
        deviceType: 'dry',
        calibrationStatus: 'calibrated',
        isCurrent: true,
        calibrationData: {
          points: [
            { spl: 55, gainOffset: -10, digitalGain: -10, baseLevel: -30, finalLevel: -40 },
            { spl: 65, gainOffset: 0, digitalGain: 0, baseLevel: -30, finalLevel: -30 },
          ],
        },
      })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/spl?page=1&per_page=1000`)
      expect(init.method).toBe('GET')
    })
  })

  describe('fetchSplStats', () => {
    it('GET /spl/stats 映射 associated_devices → associatedDevices', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: { total: 3, calibrated: 2, uncalibrated: 1, associated_devices: 3 },
        })
      )
      const stats = await fetchSplStats()
      expect(stats).toEqual({
        total: 3,
        calibrated: 2,
        uncalibrated: 1,
        associatedDevices: 3,
      })
      expect(lastCall()[0]).toBe(`${API_BASE_URL}/spl/stats`)
    })
  })

  describe('fetchPlaybackDeviceRefs', () => {
    it('GET /playback-devices 带 per_page=1000，items 映射 PlaybackDeviceRef', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: {
            items: [
              { id: 1, name: '音箱0°', model: 'RME Fireface 802', device_type: 'dry' },
              { id: 2, name: '音箱90°', model: 'RME Fireface 802', device_type: 'noise' },
            ],
            total: 2,
          },
        })
      )
      const refs = await fetchPlaybackDeviceRefs()
      expect(refs).toEqual([
        { id: 1, name: '音箱0°', model: 'RME Fireface 802', deviceType: 'dry' },
        { id: 2, name: '音箱90°', model: 'RME Fireface 802', deviceType: 'noise' },
      ])
      const [url] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/playback-devices?page=1&per_page=1000`)
    })
  })

  describe('fetchSplHistory', () => {
    it('GET /spl/{id}/history 映射 items', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: {
            items: [
              {
                id: 11,
                calibration_data: {
                  points: [{ spl: 65, gain_offset: 0, digital_gain: 0, base_level: -30, final_level: -30 }],
                },
                distance: 1,
                test_frequency: 1000,
                created_at: '2026-10-10T14:05:00Z',
              },
            ],
            total: 1,
          },
        })
      )
      const history = await fetchSplHistory(5)
      expect(history).toHaveLength(1)
      expect(history[0]).toMatchObject({
        id: 11,
        distance: 1,
        testFrequency: 1000,
        calibrationData: { points: [{ spl: 65, gainOffset: 0, digitalGain: 0 }] },
      })
      expect(lastCall()[0]).toBe(`${API_BASE_URL}/spl/5/history`)
    })
  })

  describe('createSplMapping', () => {
    it('POST /spl 提交 snake_case 请求体，返回 IdData', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: 'SPL 映射记录创建成功', data: { id: 17 } }, 201)
      )
      const result = await createSplMapping({
        name: '新映射',
        description: null,
        deviceId: 1,
        deviceType: 'dry',
        distance: 1.0,
        targetSpl: 65,
        digitalGain: 2.5,
        testFrequency: 1000,
        calibrationStatus: null,
        calibrationData: {
          points: [{ spl: 55, gainOffset: -10, digitalGain: -10, baseLevel: -30, finalLevel: -40 }],
        },
        isCurrent: false,
      })
      expect(result).toEqual({ id: 17 })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/spl`)
      expect(init.method).toBe('POST')
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      expect(body).toMatchObject({
        name: '新映射',
        device_id: 1,
        device_type: 'dry',
        distance: 1.0,
        target_spl: 65,
        digital_gain: 2.5,
        test_frequency: 1000,
        calibration_data: {
          points: [{ spl: 55, gain_offset: -10, digital_gain: -10, base_level: -30, final_level: -40 }],
        },
      })
      expect(body).not.toHaveProperty('is_current')
    })
  })

  describe('updateSplMapping', () => {
    it('PUT /spl/{id} 提交 snake_case 请求体（校准数据键转 snake_case）', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: 'SPL 映射记录更新成功' })
      )
      await updateSplMapping(5, {
        name: '改名',
        distance: 1.5,
        calibrationData: {
          points: [{ spl: 65, gainOffset: 0, digitalGain: 0, baseLevel: -30, finalLevel: -30 }],
        },
        calibrationStatus: 'uncalibrated',
        isCurrent: false,
      })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/spl/5`)
      expect(init.method).toBe('PUT')
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      expect(body).toMatchObject({
        name: '改名',
        distance: 1.5,
        calibration_status: 'uncalibrated',
        calibration_data: { points: [{ spl: 65, gain_offset: 0 }] },
      })
      expect(body).toHaveProperty('is_current')
    })

    it('校准数据显式清除（null）以空点集 { points: [] } 表达', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: 'SPL 映射记录更新成功' })
      )
      await updateSplMapping(5, { calibrationData: null, calibrationStatus: 'uncalibrated' })
      const body = JSON.parse(String(lastCall()[1].body)) as {
        calibration_data: { points: unknown[] }
      }
      expect(body.calibration_data).toEqual({ points: [] })
    })
  })

  describe('deleteSplMapping', () => {
    it('DELETE /spl/{id} 成功返回 { success: true }', async () => {
      queueResponses(
        jsonResponse({ success: true, code: 0, message: 'SPL 映射记录已删除' })
      )
      const result = await deleteSplMapping(5)
      expect(result).toEqual({ success: true })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/spl/5`)
      expect(init.method).toBe('DELETE')
    })
  })

  describe('calibrateSplMapping', () => {
    it('POST /spl/{id}/calibrate（无请求体），SplCalibrationResult 映射 success/calibrationStatus', async () => {
      queueResponses(
        jsonResponse({
          success: true,
          code: 0,
          data: { id: 5, calibration_status: 'calibrated' },
        })
      )
      const result = await calibrateSplMapping(5)
      expect(result).toEqual({ success: true, calibrationStatus: 'calibrated' })
      const [url, init] = lastCall()
      expect(url).toBe(`${API_BASE_URL}/spl/5/calibrate`)
      expect(init.method).toBe('POST')
      expect(init.body).toBeUndefined()
    })
  })
})
