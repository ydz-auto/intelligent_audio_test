/**
 * INT-899（INT-858 N1）：错误消息安全化工具——原始 gRPC/RPC 异常文本不直出页面/Toast。
 */
import { describe, it, expect } from 'vitest'
import {
  isRawRpcErrorText,
  toUserErrorMessage,
  toUserErrorDetail,
} from '../errorMessage'

/** 与后端 api_gateway 透传一致的原始 gRPC 异常文本（算法 50067 拒连） */
const RAW_RPC_MESSAGE =
  '<_InactiveRpcError of RPC that terminated with:\n' +
  '\tstatus = StatusCode.UNAVAILABLE\n' +
  '\tdetails = "failed to connect to all addresses; last error: UNAVAILABLE: ipv4:127.0.0.1:50067: ' +
  'WSAGetOverlappedResult: Connection refused"\n' +
  '\tdebug_error_string = "UNAVAILABLE:failed to connect to all addresses"\n' +
  '>'

describe('isRawRpcErrorText', () => {
  it('识别原始 gRPC/RPC 异常签名', () => {
    expect(isRawRpcErrorText(RAW_RPC_MESSAGE)).toBe(true)
  })

  it('正常业务错误文案不被误判', () => {
    expect(isRawRpcErrorText('类型已存在')).toBe(false)
    expect(isRawRpcErrorText('网络断开')).toBe(false)
    expect(isRawRpcErrorText('')).toBe(false)
  })

  it('INT-974：浏览器级网络失败（fetch TypeError）识别为内部异常', () => {
    expect(isRawRpcErrorText('Failed to fetch')).toBe(true)
  })
})

describe('toUserErrorMessage', () => {
  it('原始 gRPC 异常 Error → 固定友好文案（不直出原文）', () => {
    expect(toUserErrorMessage(new Error(RAW_RPC_MESSAGE), '算法服务暂不可用，请稍后重试'))
      .toBe('算法服务暂不可用，请稍后重试')
  })

  it('原始异常在 detail 字段（message 为通用文案）→ 同样降级', () => {
    const err = new Error('API Request failed') as any
    err.detail = RAW_RPC_MESSAGE
    expect(toUserErrorMessage(err, '重载失败')).toBe('重载失败')
  })

  it('正常业务错误 → 原样返回（单行化）', () => {
    expect(toUserErrorMessage(new Error('网络断开'), '保存失败')).toBe('网络断开')
    expect(toUserErrorMessage(new Error('类型已存在'), '保存失败')).toBe('类型已存在')
  })

  it('INT-974：fetch 网络失败 TypeError → 固定友好文案', () => {
    expect(toUserErrorMessage(new Error('Failed to fetch'), '日志加载失败，请稍后重试'))
      .toBe('日志加载失败，请稍后重试')
  })

  it('多行业务文案单行化，超长截断 200 字符', () => {
    const long = `第${'x'.repeat(260)}行`
    const out = toUserErrorMessage(new Error(`第一行\n第二行\n${long}`), '兜底')
    expect(out).not.toContain('\n')
    expect(out.length).toBeLessThanOrEqual(200)
  })

  it('取不到消息 → fallback', () => {
    expect(toUserErrorMessage(undefined, '保存失败')).toBe('保存失败')
    expect(toUserErrorMessage({}, '保存失败')).toBe('保存失败')
  })
})

describe('toUserErrorDetail', () => {
  it('原始 gRPC 异常 → 返回完整原文（detail 优先）', () => {
    const err = new Error(RAW_RPC_MESSAGE) as any
    err.detail = RAW_RPC_MESSAGE
    expect(toUserErrorDetail(err)).toBe(RAW_RPC_MESSAGE)
  })

  it('正常业务错误 → 空串（不显示 Toast 折叠区）', () => {
    expect(toUserErrorDetail(new Error('网络断开'))).toBe('')
  })
})
