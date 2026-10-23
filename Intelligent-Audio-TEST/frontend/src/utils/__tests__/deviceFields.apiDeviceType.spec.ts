/**
 * INT-1434：generateDeviceFields('api') 含 deviceType（被测设备类型）字段——
 * 决定执行路由（http_api / websocket_api），留空按端点协议自动派生（autoDerive）。
 */
import { describe, it, expect } from 'vitest'
import { generateDeviceFields } from '../deviceFields'

const fields = generateDeviceFields('api')
const deviceType = fields.find(f => f.key === 'deviceType')

describe('generateDeviceFields("api") 被测设备类型（INT-1434）', () => {
  it('包含 deviceType 下拉（http_api / websocket_api 两选项，非必填）', () => {
    expect(deviceType).toBeDefined()
    expect(deviceType!.type).toBe('select')
    expect(deviceType!.required).toBeFalsy()
    expect(deviceType!.options).toEqual([
      { value: 'http_api', label: 'HTTP API' },
      { value: 'websocket_api', label: 'WebSocket API' },
    ])
  })

  it('deviceType 标记 autoDerive（端点协议自动派生，缺省 http_api）', () => {
    expect(deviceType!.autoDerive).toBe(true)
    expect(deviceType!.defaultValue).toBe('')
  })
})
