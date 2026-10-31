/**
 * INT-1800 / B0《09_API协议面与执行道契约》：协议 × 流式性两维的领域口径单测。
 * 锁定：4 值协议词表、可用矩阵（A3 / INT-1791 + A4 / INT-2079 = 后端七组合同一张表）、
 * 流式开关锁定、亲和域令牌只由 streaming 派生。
 */
import { describe, expect, it } from 'vitest'

import {
  API_PROTOCOLS,
  API_PROTOCOL_LABEL,
  DEFAULT_API_PROTOCOL,
  DEFAULT_API_STREAMING,
  apiProtocolOptions,
  defaultStreamingFor,
  deriveAffinityDeviceType,
  isApiProtocol,
  isCombinationImplemented,
  isProtocolImplemented,
  isStreamingLocked,
  streamingLabel,
  unavailableCombinationReason,
} from '@/domain/models/apiProtocol'

describe('协议值域（B0 §3.2.1：只存规范值 4 个）', () => {
  it('值域恰为 http / websocket / sse / grpc，且都有中文展示名', () => {
    expect([...API_PROTOCOLS]).toEqual(['http', 'websocket', 'sse', 'grpc'])
    for (const protocol of API_PROTOCOLS) {
      expect(API_PROTOCOL_LABEL[protocol]).toBeTruthy()
    }
  })

  it('isApiProtocol 拒绝 https / ws / wss / 大写等非规范值', () => {
    expect(isApiProtocol('http')).toBe(true)
    expect(isApiProtocol('websocket')).toBe(true)
    for (const invalid of ['https', 'ws', 'wss', 'HTTP', '', null, undefined, 1]) {
      expect(isApiProtocol(invalid)).toBe(false)
    }
  })

  it('默认值 = 后端写侧缺省 http / 非流式', () => {
    expect(DEFAULT_API_PROTOCOL).toBe('http')
    expect(DEFAULT_API_STREAMING).toBe(false)
  })
})

describe('可用矩阵（A3 / INT-1791 + A4 / INT-2079：与后端 AVAILABLE_PROTOCOL_STREAMING 同一张七组合表）', () => {
  const expected: Record<string, boolean> = {
    'http:false': true,
    'http:true': true,
    'websocket:false': true,
    'websocket:true': true,
    'sse:false': false,
    'sse:true': true,
    'grpc:false': true,
    'grpc:true': true,
  }

  it('8 种组合逐一对照后端写侧矩阵', () => {
    for (const protocol of API_PROTOCOLS) {
      for (const streaming of [false, true]) {
        expect(isCombinationImplemented(protocol, streaming)).toBe(
          expected[`${protocol}:${streaming}`]
        )
      }
    }
  })

  it('四个协议都至少有一条可写组合（A1 gRPC + A2 SSE 上线后不再置灰）', () => {
    for (const protocol of API_PROTOCOLS) {
      expect(isProtocolImplemented(protocol)).toBe(true)
    }
    expect(isProtocolImplemented('https')).toBe(false)
  })

  it('流式开关仅在协议有多种可写形态时解锁', () => {
    expect(isStreamingLocked('http')).toBe(false)
    expect(isStreamingLocked('grpc')).toBe(false)
    expect(isStreamingLocked('websocket')).toBe(false)
    expect(isStreamingLocked('sse')).toBe(true)
    expect(isStreamingLocked('https')).toBe(true)
  })

  it('切协议的流式性缺省：websocket / sse → 流式，http / grpc → 非流式', () => {
    expect(defaultStreamingFor('http')).toBe(false)
    expect(defaultStreamingFor('websocket')).toBe(true)
    expect(defaultStreamingFor('sse')).toBe(true)
    expect(defaultStreamingFor('grpc')).toBe(false)
    expect(defaultStreamingFor('https')).toBe(false)
  })

  it('不可用组合的提示文案与后端 400 口径一致', () => {
    expect(unavailableCombinationReason('http', false)).toBeNull()
    expect(unavailableCombinationReason('http', true)).toBeNull()
    expect(unavailableCombinationReason('websocket', true)).toBeNull()
    expect(unavailableCombinationReason('sse', true)).toBeNull()
    expect(unavailableCombinationReason('grpc', false)).toBeNull()
    expect(unavailableCombinationReason('grpc', true)).toBeNull()
    expect(unavailableCombinationReason('sse', false)).toBe(
      '协议 sse 与流式性 streaming=false 的组合实现未上线'
    )
    // A4（INT-2079）：websocket + 非流式（请求-响应）已上线，不再报未实现
    expect(unavailableCombinationReason('websocket', false)).toBeNull()
    expect(unavailableCombinationReason('https', false)).toBe('协议取值非法')
  })

  it('下拉选项：4 项全列，均不置灰', () => {
    expect(apiProtocolOptions()).toEqual([
      { value: 'http', label: 'HTTP', disabled: false },
      { value: 'websocket', label: 'WebSocket', disabled: false },
      { value: 'sse', label: 'SSE', disabled: false },
      { value: 'grpc', label: 'gRPC', disabled: false },
    ])
  })
})

describe('两维展示与派生', () => {
  it('流式性文案固定为「流式 / 非流式」', () => {
    expect(streamingLabel(true)).toBe('流式')
    expect(streamingLabel(false)).toBe('非流式')
  })

  it('亲和域令牌只由 streaming 派生（B0 §3.3）：流式 → websocket_api，非流式 → http_api', () => {
    expect(deriveAffinityDeviceType(true)).toBe('websocket_api')
    expect(deriveAffinityDeviceType(false)).toBe('http_api')
  })
})
