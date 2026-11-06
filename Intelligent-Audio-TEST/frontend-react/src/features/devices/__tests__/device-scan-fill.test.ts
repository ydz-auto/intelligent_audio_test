/**
 * INT-1029 抽屉内扫描回填（mergeScanPrefill）单测：
 * 对齐 V9.7.10 useDeviceSelection.selectDevice 口径——
 *  - 名称编辑态保留用户已填值，为空时取扫描值；
 *  - 硬件字段（型号/序列号/系统/系统版本/应用名/应用版本/IP；播放：唯一ID/通道/采样率/类型）以扫描值为准；
 *  - 非扫描字段（备注/优先级/算法等）保持原值不动。
 */
import { describe, expect, it, vi } from 'vitest'
import type { useForm } from 'react-hook-form'

import { mergeScanPrefill } from '@/features/devices/components/modals/device-mutate-drawer'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'

type AnyForm = ReturnType<typeof useForm<any>>

function makeForm(current: Record<string, unknown>) {
  const reset = vi.fn()
  const form = {
    getValues: () => current,
    reset,
  } as unknown as AnyForm
  return { form, reset }
}

describe('mergeScanPrefill（INT-1029 抽屉内扫描回填）', () => {
  it('测试设备：编辑态名称保留用户已填值，硬件字段以扫描值为准', () => {
    const current = {
      kind: 'test',
      name: '我的设备名',
      model: '原型号',
      system: 'Android',
      systemVersion: '9',
      appName: '旧应用',
      appVersion: '1.0',
      serialNumber: 'OLD_SERIAL',
      ip: '10.0.0.1',
      remark: '备注保留',
      priority: 5,
    }
    const { form, reset } = makeForm(current)
    const prefill: Partial<TestDevice> = {
      name: 'Android Unknown Android',
      model: 'Unknown Android',
      serialNumber: 'List',
      system: 'Android',
      systemVersion: 'Unknown',
      appName: 'Default App',
      appVersion: '1.0',
      ip: '192.168.1.10',
    }
    mergeScanPrefill(form, 'test', prefill)
    expect(reset).toHaveBeenCalledTimes(1)
    const merged = reset.mock.calls[0][0]
    expect(merged.name).toBe('我的设备名') // 名称保留用户已填值（V9.7.10 isEditMode 语义）
    expect(merged.model).toBe('Unknown Android')
    expect(merged.serialNumber).toBe('List')
    expect(merged.system).toBe('Android')
    expect(merged.systemVersion).toBe('Unknown')
    expect(merged.appName).toBe('Default App')
    expect(merged.ip).toBe('192.168.1.10')
    expect(merged.remark).toBe('备注保留') // 非扫描字段不动
    expect(merged.priority).toBe(5)
  })

  it('测试设备：新增态名称为空时取扫描名称', () => {
    const current = {
      kind: 'test',
      name: '',
      model: '',
      system: 'Android',
      systemVersion: '',
      appName: '',
      appVersion: '',
      serialNumber: '',
      ip: '',
    }
    const { form, reset } = makeForm(current)
    mergeScanPrefill(form, 'test', {
      name: '扫描到的设备',
      model: 'P50',
      serialNumber: 'SN001',
      system: 'HarmonyOS',
      systemVersion: '3.0',
      appName: 'App',
      appVersion: '2.0',
    } as Partial<TestDevice>)
    const merged = reset.mock.calls[0][0]
    expect(merged.name).toBe('扫描到的设备')
    expect(merged.system).toBe('HarmonyOS')
    expect(merged.systemVersion).toBe('3.0')
  })

  it('播放设备：回填唯一ID/通道/采样率/类型，名称保留已填值', () => {
    const current = {
      kind: 'playback',
      name: '播放设备A',
      model: 'M300',
      deviceUniqueId: 'OLD_UID',
      channelIndex: '1',
      sampleRate: '48000',
      deviceType: 'dry',
    }
    const { form, reset } = makeForm(current)
    const prefill: Partial<PlaybackDevice> = {
      name: 'AudioChannel 2',
      model: 'USB Audio',
      deviceUniqueId: 'audio-2',
      channelIndex: 2,
      sampleRate: 44100,
      deviceType: 'noise',
    }
    mergeScanPrefill(form, 'playback', prefill)
    const merged = reset.mock.calls[0][0]
    expect(merged.name).toBe('播放设备A')
    expect(merged.model).toBe('USB Audio')
    expect(merged.deviceUniqueId).toBe('audio-2')
    expect(merged.channelIndex).toBe('2') // 数字归一字符串
    expect(merged.sampleRate).toBe('44100')
    expect(merged.deviceType).toBe('noise')
  })

  it('api 页签：不落任何回填（API 不支持扫描，§11-11）', () => {
    const current = { kind: 'api', name: '语音识别 API' }
    const { form, reset } = makeForm(current)
    mergeScanPrefill(form, 'api', {} as Partial<TestDevice>)
    expect(reset).not.toHaveBeenCalled()
  })
})
