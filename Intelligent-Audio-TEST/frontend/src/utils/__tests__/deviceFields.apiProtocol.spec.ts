/**
 * INT-2025：generateDeviceFields('api') 的「协议 × 流式性」两维字段。
 *
 * 背景：后端 device_type 已废弃（写侧非空即 400），协议改由顶层 protocol 列 +
 * streaming 布尔列表达。表单不再出现 deviceType 字段。
 */
import { describe, it, expect } from 'vitest'
import { generateDeviceFields } from '../deviceFields'

const fields = generateDeviceFields('api')
const protocol = fields.find(f => f.key === 'protocol')
const streaming = fields.find(f => f.key === 'streaming')

describe('generateDeviceFields("api") 协议 × 流式性（INT-2025）', () => {
  it('不再出现已废弃的 deviceType 字段', () => {
    expect(fields.find(f => f.key === 'deviceType')).toBeUndefined()
  })

  it('包含协议下拉：http / websocket / sse / grpc 四值，必填，缺省 http', () => {
    expect(protocol).toBeDefined()
    expect(protocol!.type).toBe('select')
    expect(protocol!.required).toBe(true)
    expect(protocol!.defaultValue).toBe('http')
    expect((protocol!.options || []).map(o => o.value)).toEqual(['http', 'websocket', 'sse', 'grpc'])
  })

  it('包含流式性字段：布尔两选，缺省非流式', () => {
    expect(streaming).toBeDefined()
    expect(streaming!.defaultValue).toBe(false)
    expect((streaming!.options || []).map(o => o.value)).toEqual([true, false])
  })
})
