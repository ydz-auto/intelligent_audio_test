import { describe, expect, it } from 'vitest'

import {
  apiDeviceFormSchema,
  playbackDeviceFormSchema,
  testDeviceFormSchema,
} from '@/features/devices/lib/device-form-schema'

describe('设备表单 schema（16_设备域.md §6.2 必填口径；AGENTS §3.7 RHF+zod）', () => {
  it('测试设备必填项缺失时校验失败（P2-11 返修）', () => {
    const result = testDeviceFormSchema.safeParse({
      name: '',
      description: '',
      remark: '',
      model: '',
      deviceType: 'physical',
      system: 'Android',
      systemVersion: '',
      apiLevel: '',
      appName: '',
      appVersion: '',
      connectionType: 'usb',
      serialNumber: '',
      ip: '',
      port: '5555',
      needsPromptAudio: false,
      algorithms: [],
      tags: [],
      priority: '5',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.map((i) => i.path[0])).toContain('name')
      expect(result.error.issues.map((i) => i.path[0])).toContain('model')
      expect(result.error.issues.map((i) => i.path[0])).toContain('systemVersion')
      expect(result.error.issues.map((i) => i.path[0])).toContain('serialNumber')
    }
  })

  it('播放设备必填项缺失时校验失败（设备类型/系统唯一标识/采样率）', () => {
    const result = playbackDeviceFormSchema.safeParse({
      name: '参考音源',
      description: '',
      model: 'Audio Gen Pro',
      deviceType: '',
      deviceUniqueId: '',
      channelIndex: '0',
      supportedChannels: '',
      supportedFormats: [],
      sampleRate: '',
      splMappingId: '',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path[0])
      expect(paths).toContain('deviceType')
      expect(paths).toContain('deviceUniqueId')
      expect(paths).toContain('sampleRate')
    }
  })

  it('API 必填项缺失时校验失败（API名称/端点/协议/算法）', () => {
    const result = apiDeviceFormSchema.safeParse({
      name: '',
      description: '',
      vendor: '',
      apiUrl: '',
      protocol: '',
      environment: 'testing',
      algorithmType: '',
      maxProcess: '5',
      maxTimeout: '30',
      maxAudioDuration: '60',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path[0])
      expect(paths).toContain('name')
      expect(paths).toContain('apiUrl')
      expect(paths).toContain('protocol')
      expect(paths).toContain('algorithmType')
    }
  })

  it('合法提交通过校验', () => {
    expect(
      testDeviceFormSchema.safeParse({
        name: '音箱-客厅位',
        description: '',
        remark: '',
        model: '旗舰 S1',
        deviceType: 'physical',
        system: 'Android',
        systemVersion: '12',
        apiLevel: '',
        appName: '音乐播放器',
        appVersion: '2.4.0',
        connectionType: 'usb',
        serialNumber: 'SN-A001',
        ip: '',
        port: '5555',
        needsPromptAudio: false,
        algorithms: ['asr_streaming'],
        tags: [],
        priority: '5',
      }).success
    ).toBe(true)
  })
})
