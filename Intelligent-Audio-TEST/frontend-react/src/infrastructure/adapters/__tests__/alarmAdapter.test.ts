import { describe, expect, it } from 'vitest'

import { formatStatusDetail, statusEventFromDto } from '@/infrastructure/adapters/alarmAdapter'
import type { DeviceStatusHistoryDto } from '@/infrastructure/dto/alarm.dto'

const BASE_DTO: DeviceStatusHistoryDto = {
  id: 1,
  device_id: 79,
  device_name: '接线测试_设备',
  event_type: 'operation',
  from_status: null,
  to_status: null,
  source: 'operation',
  result: 'failed',
  detail: null,
  created_at: '2026-10-23T08:00:00',
}

describe('status-history detail 归一（P2-5：detail 为对象时不得直接当 React 子节点）', () => {
  it('字符串原样保留并去首尾空白', () => {
    expect(formatStatusDetail(' serial_number: JX1495 ')).toBe('serial_number: JX1495')
  })

  it('空串 / null / 空对象归一为 null', () => {
    expect(formatStatusDetail('   ')).toBeNull()
    expect(formatStatusDetail(null)).toBeNull()
    expect(formatStatusDetail(undefined)).toBeNull()
    expect(formatStatusDetail({})).toBeNull()
  })

  it('对象按 key: value 拼接（实测两种形态）', () => {
    expect(formatStatusDetail({ serial_number: 'JX1495V213937' })).toBe(
      'serial_number: JX1495V213937'
    )
    expect(formatStatusDetail({ operation: 'install_app', error: 'device not found' })).toBe(
      'operation: install_app；error: device not found'
    )
  })

  it('嵌套值 JSON 化，不产生 [object Object]', () => {
    const text = formatStatusDetail({ payload: { file_path: '/sdcard/a.apk' } })
    expect(text).toBe('payload: {"file_path":"/sdcard/a.apk"}')
  })

  it('适配器产出 domain detail 恒为 string | null', () => {
    const event = statusEventFromDto({ ...BASE_DTO, detail: { serial_number: 'JX1495V213937' } })
    expect(typeof event.detail).toBe('string')
    expect(event.detail).toBe('serial_number: JX1495V213937')
  })
})
