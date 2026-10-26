/**
 * INT-2025：API 协议 × 流式性纯函数（与后端 AVAILABLE_PROTOCOL_STREAMING 同表）。
 */
import { describe, it, expect } from 'vitest'
import {
  API_PROTOCOLS,
  DEFAULT_API_PROTOCOL,
  DEFAULT_API_STREAMING,
  defaultStreamingFor,
  isApiProtocol,
  isStreamingLocked,
  streamingLabel,
} from '../apiProtocol'

describe('INT-2025：apiProtocol', () => {
  it('协议规范值域为 http / websocket / sse / grpc', () => {
    expect([...API_PROTOCOLS]).toEqual(['http', 'websocket', 'sse', 'grpc'])
    expect(isApiProtocol('http')).toBe(true)
    expect(isApiProtocol('https')).toBe(false)
    expect(isApiProtocol(null)).toBe(false)
  })

  it('缺省协议 http、缺省非流式（与后端写侧缺省一致）', () => {
    expect(DEFAULT_API_PROTOCOL).toBe('http')
    expect(DEFAULT_API_STREAMING).toBe(false)
  })

  it('切换协议的流式性缺省：websocket / sse → true；http / grpc → false', () => {
    expect(defaultStreamingFor('websocket')).toBe(true)
    expect(defaultStreamingFor('sse')).toBe(true)
    expect(defaultStreamingFor('http')).toBe(false)
    expect(defaultStreamingFor('grpc')).toBe(false)
  })

  it('websocket / sse 流式性锁定；http / grpc 可切换；非法协议视为锁定', () => {
    expect(isStreamingLocked('websocket')).toBe(true)
    expect(isStreamingLocked('sse')).toBe(true)
    expect(isStreamingLocked('http')).toBe(false)
    expect(isStreamingLocked('grpc')).toBe(false)
    expect(isStreamingLocked('https')).toBe(true)
  })

  it('流式性展示文案', () => {
    expect(streamingLabel(true)).toBe('流式')
    expect(streamingLabel(false)).toBe('非流式')
  })
})
