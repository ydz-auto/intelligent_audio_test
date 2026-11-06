/**
 * INT-1581 格式转换附加参数契约：convertAudio（POST /audios/{id}/convert）。
 * camelCase Domain → ConvertFormatRequest snake_case wire（format/sample_rate/
 * channels/bit_depth/bitrate）；未选参数不发送（后端全部可选，缺省仅转换格式）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import { convertAudio } from '@/infrastructure/api/audios-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function bodyOfCall(): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return JSON.parse(String(init.body)) as Record<string, unknown>
}

describe('convertAudio 附加参数契约（INT-1581）', () => {
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

  it('无损格式：提交 format/sample_rate/channels/bit_depth', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, code: 0, data: null }))
    await convertAudio(12, {
      format: 'WAV',
      sampleRate: 16000,
      channels: 1,
      bitDepth: 24,
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/audios/12/convert`)
    expect(init.method).toBe('POST')
    expect(bodyOfCall()).toEqual({
      format: 'WAV',
      sample_rate: 16000,
      channels: 1,
      bit_depth: 24,
    })
  })

  it('有损格式：提交 format/sample_rate/channels/bitrate（kbps）', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, code: 0, data: null }))
    await convertAudio(12, {
      format: 'MP3',
      sampleRate: 44100,
      channels: 2,
      bitrate: 320,
    })

    expect(bodyOfCall()).toEqual({
      format: 'MP3',
      sample_rate: 44100,
      channels: 2,
      bitrate: 320,
    })
  })

  it('未选附加参数时不发送对应键（保持后端仅转换格式的原行为）', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, code: 0, data: null }))
    await convertAudio(12, { format: 'FLAC' })

    expect(bodyOfCall()).toEqual({ format: 'FLAC' })
  })
})
