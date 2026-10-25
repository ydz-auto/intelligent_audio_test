/**
 * INT-1800 / B0《09_API协议面与执行道契约》：协议 × 流式性两维的领域口径单测。
 * 锁定：4 值协议词表、可用矩阵（只有 http+非流式、websocket+流式）、
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

describe('可用矩阵（B0 §3.2.3：B1 上线时只放行两条组合）', () => {
  const expected: Record<string, boolean> = {
    'http:false': true,
    'http:true': false,
    'websocket:false': false,
    'websocket:true': true,
    'sse:false': false,
    'sse:true': false,
    'grpc:false': false,
    'grpc:true': false,
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

  it('sse / grpc 未上线 → 协议级不可用；http / websocket 至少一条组合可用', () => {
    expect(isProtocolImplemented('http')).toBe(true)
    expect(isProtocolImplemented('websocket')).toBe(true)
    expect(isProtocolImplemented('sse')).toBe(false)
    expect(isProtocolImplemented('grpc')).toBe(false)
    expect(isProtocolImplemented('https')).toBe(false)
  })

  it('流式开关仅在协议有多种可写形态时解锁（当前全部锁定）', () => {
    expect(isStreamingLocked('http')).toBe(true)
    expect(isStreamingLocked('websocket')).toBe(true)
    expect(isStreamingLocked('sse')).toBe(true)
    expect(isStreamingLocked('grpc')).toBe(true)
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
    expect(unavailableCombinationReason('websocket', true)).toBeNull()
    expect(unavailableCombinationReason('sse', true)).toBe('协议实现未上线')
    expect(unavailableCombinationReason('grpc', false)).toBe('协议实现未上线')
    expect(unavailableCombinationReason('http', true)).toBe(
      '协议 http 与流式性 streaming=true 的组合实现未上线'
    )
    expect(unavailableCombinationReason('websocket', false)).toBe(
      '协议 websocket 与流式性 streaming=false 的组合实现未上线'
    )
    expect(unavailableCombinationReason('https', false)).toBe('协议取值非法')
  })

  it('下拉选项：4 项全列，sse / grpc 置灰', () => {
    expect(apiProtocolOptions()).toEqual([
      { value: 'http', label: 'HTTP', disabled: false },
      { value: 'websocket', label: 'WebSocket', disabled: false },
      { value: 'sse', label: 'SSE', disabled: true },
      { value: 'grpc', label: 'gRPC', disabled: true },
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
