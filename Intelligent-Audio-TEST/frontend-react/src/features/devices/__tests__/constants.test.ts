import { describe, expect, it } from 'vitest'

import {
  DEVICES_ADD_BUTTON_LABEL,
  DEVICES_SEARCH_PLACEHOLDER,
  DEVICES_STATS_LABELS,
  DEVICES_TABS,
  DEVICES_TAB_WHITELIST,
} from '@/features/devices/constants'

describe('devices constants（16_设备域.md §9 中文文案）', () => {
  it('三页签白名单与权限码与 §3.2 一致', () => {
    expect(DEVICES_TAB_WHITELIST).toEqual(['test', 'playback', 'api'])
    expect(DEVICES_TABS.map((tab) => tab.value)).toEqual(['test', 'playback', 'api'])
    expect(DEVICES_TABS.map((tab) => tab.label)).toEqual(['测试设备', '播放设备', '测试 API'])
    expect(DEVICES_TABS[0].requiredPermission).toBe('device:read')
    expect(DEVICES_TABS[1].requiredPermission).toBe('playback:read')
    expect(DEVICES_TABS[2].requiredPermission).toBe('api_config:read')
  })

  it('主按钮文案随页签（§9：添加测试设备/添加播放设备/添加测试API）', () => {
    expect(DEVICES_ADD_BUTTON_LABEL.test).toBe('添加测试设备')
    expect(DEVICES_ADD_BUTTON_LABEL.playback).toBe('添加播放设备')
    expect(DEVICES_ADD_BUTTON_LABEL.api).toBe('添加测试API')
  })

  it('搜索占位逐页签（§9）', () => {
    expect(DEVICES_SEARCH_PLACEHOLDER.test).toContain('设备名称')
    expect(DEVICES_SEARCH_PLACEHOLDER.playback).toContain('播放设备名称')
    expect(DEVICES_SEARCH_PLACEHOLDER.api).toContain('API 名称')
  })

  it('统计徽章文案（§9：测试/播放 四枚；API 页签含「测试中API」）', () => {
    expect(DEVICES_STATS_LABELS.test).toEqual(['总设备数', '在线设备', '离线设备', '异常设备'])
    expect(DEVICES_STATS_LABELS.playback).toEqual(['总设备数', '在线设备', '离线设备', '异常设备'])
    expect(DEVICES_STATS_LABELS.api).toEqual(['总测试API数', '可用API', '不可用API', '测试中API'])
  })
})
