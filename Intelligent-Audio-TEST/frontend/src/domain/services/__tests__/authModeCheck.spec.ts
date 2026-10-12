/**
 * authModeCheck 单元测试 —— 认证模式启动自检比对逻辑（INT-180）
 * 纯领域函数：错位判真、不可比静默、非法后端取值标注。
 */
import { describe, it, expect } from 'vitest'
import { checkAuthMode } from '../authModeCheck'
import { getEffectiveAuthMode, AuthMode } from '@/domain/enums'

describe('checkAuthMode', () => {
  it('两侧一致 → 静默（mismatch=false）', () => {
    expect(checkAuthMode(AuthMode.DEV, AuthMode.DEV)).toEqual({
      mismatch: false,
      frontendMode: 'dev',
      backendMode: 'dev',
      backendModeKnown: true,
    })
    expect(checkAuthMode(AuthMode.OFF, AuthMode.OFF).mismatch).toBe(false)
    expect(checkAuthMode(AuthMode.PROD, AuthMode.PROD).mismatch).toBe(false)
  })

  it('两侧错位 → mismatch=true 且携带两侧当前值', () => {
    const result = checkAuthMode(AuthMode.OFF, AuthMode.DEV)
    expect(result.mismatch).toBe(true)
    expect(result.frontendMode).toBe('off')
    expect(result.backendMode).toBe('dev')
    expect(result.backendModeKnown).toBe(true)
  })

  it('后端未回值（旧后端/空串）→ 不可比，静默', () => {
    expect(checkAuthMode(AuthMode.DEV, '').mismatch).toBe(false)
    expect(checkAuthMode(AuthMode.DEV, '   ').mismatch).toBe(false)
  })

  it('后端取值不在合法枚举集合 → 错位且 backendModeKnown=false', () => {
    const result = checkAuthMode(AuthMode.DEV, 'staging')
    expect(result.mismatch).toBe(true)
    expect(result.backendMode).toBe('staging')
    expect(result.backendModeKnown).toBe(false)
  })

  it('后端值两侧空白 → trim 后比对', () => {
    expect(checkAuthMode(AuthMode.DEV, ' dev ').mismatch).toBe(false)
  })
})

describe('getEffectiveAuthMode', () => {
  it('未注入 VITE_AUTH_MODE（undefined）→ 回退 off（向后兼容语义与 router/client 一致）', () => {
    expect(getEffectiveAuthMode(() => undefined)).toBe(AuthMode.OFF)
  })

  it('注入空串 → 回退 off', () => {
    expect(getEffectiveAuthMode(() => '')).toBe(AuthMode.OFF)
  })

  it('显式注入 → 取注入值', () => {
    expect(getEffectiveAuthMode(() => 'dev')).toBe(AuthMode.DEV)
    expect(getEffectiveAuthMode(() => 'prod')).toBe(AuthMode.PROD)
  })
})
