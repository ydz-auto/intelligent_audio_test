/**
 * INT-655：Device 列表「实验室」facet 过滤——测试/播放设备按 lab_id 命中，
 * 「所有实验室」不参与过滤、未绑定设备恒不命中具体实验室。
 *
 * 锁定契约：
 * 1. 测试设备按 lab_id 过滤（labId 匹配选中值）；
 * 2. 播放设备按 lab_id 过滤；
 * 3. 未绑定（无 labId）设备在选中具体实验室时不出现；
 * 4. ViewMode.ALL（所有实验室）时全部命中；
 * 5. API 页签不参与实验室过滤（API 资源无 lab 维度，INT-487 口径）。
 *
 * 说明：deviceState 为真实模块（模块级 ref 可跨用例共享），deviceComputed 直接消费。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { ViewMode, DeviceTabType } from '@/domain/enums'

import {
  testDevices,
  playbackDevices,
  apiDevices,
  laboratoryFilter,
  activeTab,
} from '../deviceState'
import {
  allFilteredTestDevices,
  allFilteredPlaybackDevices,
  allFilteredAPIDevices,
} from '../deviceComputed'

beforeEach(() => {
  laboratoryFilter.value = ViewMode.ALL
  activeTab.value = DeviceTabType.TEST
  testDevices.value = [
    { id: 1, name: 'A 实验室设备', labId: 10, labName: 'A 实验室', status: 'online' },
    { id: 2, name: 'B 实验室设备', labId: 20, labName: 'B 实验室', status: 'online' },
    { id: 3, name: '未绑定设备', status: 'offline' },
  ] as any
  playbackDevices.value = [
    { id: 4, name: 'P-A 实验室', labId: 10, labName: 'A 实验室', status: 'online' },
    { id: 5, name: 'P-未绑定', status: 'online' },
  ] as any
  apiDevices.value = [
    { id: 6, name: 'API-1', algorithmType: 'ASR' },
    { id: 7, name: 'API-2', algorithmType: 'TTS' },
  ] as any
})

describe('deviceComputed 实验室 facet（INT-655）', () => {
  it('「所有实验室」时测试/播放设备全部命中', () => {
    expect(allFilteredTestDevices.value.length).toBe(3)
    expect(allFilteredPlaybackDevices.value.length).toBe(2)
  })

  it('选中具体实验室后测试设备仅保留 labId 命中项，未绑定设备不出现', () => {
    laboratoryFilter.value = '10'
    const names = allFilteredTestDevices.value.map(d => d.name)
    expect(names).toEqual(['A 实验室设备'])
  })

  it('选中具体实验室后播放设备仅保留 labId 命中项', () => {
    laboratoryFilter.value = '10'
    const names = allFilteredPlaybackDevices.value.map(d => d.name)
    expect(names).toEqual(['P-A 实验室'])
  })

  it('未绑定设备（无 labId）在选中具体实验室时被过滤', () => {
    laboratoryFilter.value = '20'
    expect(allFilteredTestDevices.value.map(d => d.name)).toEqual(['B 实验室设备'])
    expect(allFilteredPlaybackDevices.value.length).toBe(0)
  })

  it('API 页签列表不受实验室过滤影响（API 资源无 lab 维度）', () => {
    laboratoryFilter.value = '10'
    expect(allFilteredAPIDevices.value.length).toBe(2)
  })

  it('选中不存在的实验室 id 时空列表', () => {
    laboratoryFilter.value = '999'
    expect(allFilteredTestDevices.value.length).toBe(0)
    expect(allFilteredPlaybackDevices.value.length).toBe(0)
  })
})
