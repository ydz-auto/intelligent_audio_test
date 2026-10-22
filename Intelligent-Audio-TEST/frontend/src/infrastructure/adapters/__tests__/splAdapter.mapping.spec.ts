/**
 * INT-1375 回归：设备 SPL 映射 DTO → Domain 字段映射（含 test_frequency）。
 *
 * 缺陷背景（P2）：toSPLMapping 漏映射 test_frequency → testFrequency，编辑弹窗
 * 「测试频率」回显恒为 1000（useSplMapping editMapping 用 `mapping.testFrequency || 1000`
 * 兜底），用户不动该字段直接保存会把真实频率（2000/3000）静默重置为 1000。
 * 本 spec 锁定全字段 snake_case → camelCase 不被回退。
 */
import { describe, it, expect } from 'vitest'
import { toSPLMapping } from '../splAdapter'
import type { SplMappingItemDto } from '../../dto/splDto'

describe('INT-1375：toSPLMapping 测试频率字段映射', () => {
  it('snake_case test_frequency → camelCase testFrequency 透传（2000/3000 不回退）', () => {
    const domain = toSPLMapping({
      id: 5,
      name: '接线测试_INT1375_2000',
      test_frequency: 2000,
    } as SplMappingItemDto)
    expect(domain.testFrequency).toBe(2000)
  })

  it('test_frequency 缺省/null → undefined（编辑兜底 1000 仅当后端无值时生效）', () => {
    const domain = toSPLMapping({
      id: 6,
      name: '接线测试_INT1375_null',
      test_frequency: null,
    } as unknown as SplMappingItemDto)
    expect(domain.testFrequency).toBeUndefined()
  })

  it('既有映射字段不回退（id/name/device_id/distance/target_spl）', () => {
    const domain = toSPLMapping({
      id: 7,
      name: '接线测试_INT1375_full',
      device_id: 3,
      distance: 1,
      target_spl: 80,
    } as SplMappingItemDto)
    expect(domain.id).toBe(7)
    expect(domain.name).toBe('接线测试_INT1375_full')
    expect(domain.deviceId).toBe(3)
    expect(domain.distance).toBe(1)
    expect(domain.targetSpl).toBe(80)
  })
})
