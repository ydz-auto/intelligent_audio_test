/**
 * 服务状态映射纯函数测试（INT-460 返修 P2-1，交付清单#8 口径⑤）：
 * /health 响应 → 状态卡行数据；网关 /health 整卡失败 → 全卡降级「检测中」+ 提示条
 * （06_关于.md §3.1.1/§4.4：失败降级「检测中」且不阻断正文）。
 */
import { describe, expect, it } from 'vitest'

import type { AuthHealthResponse, GatewayHealthResponse } from '@/domain/models/about'

import { toServiceHealthState } from '../statusMapper'

const gatewayOk: GatewayHealthResponse = {
  status: 'ok',
  service: 'api_gateway',
  version: 'V9.7.31',
  database: 'intelligent_audio_test',
}
const authOk: AuthHealthResponse = { status: 'ok', service: 'auth_service' }

describe('toServiceHealthState', () => {
  it('网关/认证均 ok → 版本 V9.7.31 + 三行正常态 + 数据库名', () => {
    const state = toServiceHealthState({
      gateway: gatewayOk,
      auth: authOk,
      gatewayFailed: false,
      authFailed: false,
    })
    expect(state.version).toBe('V9.7.31')
    expect(state.versionTone).toBe('success')
    expect(state.gateway.badge).toBe('正常')
    expect(state.auth.badge).toBe('正常')
    expect(state.database).toBe('intelligent_audio_test')
    expect(state.anyFailure).toBe(false)
  })

  it('网关 /health 请求失败 → 版本「—」+ 三徽章「检测中」+ 提示条（全卡降级）', () => {
    const state = toServiceHealthState({
      gateway: undefined,
      auth: undefined,
      gatewayFailed: true,
      authFailed: true,
    })
    expect(state.version).toBe('—')
    expect(state.versionTone).toBe('muted')
    expect(state.gateway.badge).toBe('检测中')
    expect(state.auth.badge).toBe('检测中')
    expect(state.database).toBeNull()
    expect(state.anyFailure).toBe(true)
  })

  it('网关非 ok → 网关行异常（destructive）；认证独立判定仍正常，不拉低', () => {
    const state = toServiceHealthState({
      gateway: { ...gatewayOk, status: 'error' },
      auth: authOk,
      gatewayFailed: false,
      authFailed: false,
    })
    expect(state.versionTone).toBe('destructive')
    expect(state.gateway.tone).toBe('destructive')
    expect(state.gateway.badge).toBe('异常')
    expect(state.auth.badge).toBe('正常')
    expect(state.anyFailure).toBe(false)
  })

  it('认证失败但网关 ok → 仅认证行降级「检测中」，网关/版本保持正常', () => {
    const state = toServiceHealthState({
      gateway: gatewayOk,
      auth: undefined,
      gatewayFailed: false,
      authFailed: true,
    })
    expect(state.version).toBe('V9.7.31')
    expect(state.gateway.badge).toBe('正常')
    expect(state.auth.badge).toBe('检测中')
    expect(state.database).toBe('intelligent_audio_test')
    expect(state.anyFailure).toBe(false)
  })

  it('网关失败但认证 ok → 认证行随网关整卡降级「检测中」（网关为主卡）', () => {
    const state = toServiceHealthState({
      gateway: undefined,
      auth: authOk,
      gatewayFailed: true,
      authFailed: false,
    })
    expect(state.version).toBe('—')
    expect(state.gateway.badge).toBe('检测中')
    expect(state.auth.badge).toBe('检测中')
    expect(state.anyFailure).toBe(true)
  })
})
